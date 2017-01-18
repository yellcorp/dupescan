import collections
import operator

from dupescan import (
    fs,
    log,
    platform,
    streampool,
)


__all__ = (
    "DuplicateFinder",
    "DuplicateContentSet",
)


def noop(*args, **kwargs):
    pass


PROGRESS_CALLBACK_FREQUENCY = 0x100000
class DuplicateFinder(object):
    """Main class for detecting files with duplicate content in a set.

    After creating an instance of DuplicateFinder, use it like a function,
    passing to it a single argument - an iterator of FileEntry objects. It will
    yield a `DuplicateContentSet` for every set of files it discovers having
    the same content.
    """
    def __init__(
        self,
        content_key_func = None,
        max_open_files = None,
        buffer_size = None,
        cancel_func = None,
        logger = None,
        progress_handler = None,
        on_error = None, # TODO: name this consistently
    ):
        """Construct a new DuplicateFinder.

        Arguments:
            content_key_func (func or None): A function that uniquely
                identifies an inode. This function should accept a single
                FileEntry instance, and return any hashable, immutable value.
                The requirement is that if a and b are FileEntry objects whose
                paths are hardlinked to the same file, the same value is
                returned for fn(a) and fn(b). If they are not, then fn(a) and
                fn(b) must return different values.

                FileEntry objects which are hardlinks to the same file will be
                realized as a single FileContent instance with more than one
                FileEntry object in its .entries property.

                If this argument is None, then no attempt to identify hardlinks
                is made. Every FileContent instance in a DuplicateContentSet
                will have exactly one FileEntry.

            max_open_files (int or None): Sets the maximum number of files to
                be opened when reading from potentially duplicate files. If a
                potential set contains more files than this number, older
                filehandles will be closed before newer ones are opened.

            buffer_size (int or None): Sets the buffer size used when reading
                from and comparing potentially duplicate files.

            cancel_func (func or None): A function that can cancel a file
                comparison operation by returning True. It takes a single
                DuplicateContentSet argument and returns a bool.  It is called
                every `buffer_size` bytes (including before the first read),
                with a DuplicateContentSet containing FileContent objects that
                are all, thus far, identical in content.

            logger (log.Logger or None): A logger object used to print debug
                information.
            
            progress_handler (ProgressHandler or None): A ProgressHandler for
                reporting progress. A ProgressHandler is an object that has two
                methods: `progress(sets, bytes_read, bytes_total)` and
                `clear()`. `progress` will be called periodically during file
                reads. `sets` will be a list of DuplicateContentSet objects,
                reflecting the current state of the compare operation.
                `bytes_read` is the number of bytes read from a single
                representative file, and `bytes_total` is the file size.
                `clear` will be called immediately before any event that may
                cause other output to be printed.

            on_error (func or None): A function accepting 2 arguments:
                `error` and `path`, called whenever an error is encountered.
                `error` is an instance of EnvironmentError or one of its
                subclasses. `path` is the path involved. To propagate the
                error, reraise it from within this function. If None is
                specified, errors are ignored. In any case, the error and
                path are first sent to the `logger`.
        """

        self._content_key_func = content_key_func

        if max_open_files is not None and max_open_files >= 1:
            self._max_open_files = max_open_files
        else:
            self._max_open_files = platform.decide_max_open_files()

        if buffer_size is not None and buffer_size >= 1:
            self._buffer_size = buffer_size
        else:
            self._buffer_size = platform.DEFAULT_BUFFER_SIZE

        self._cancel_func = cancel_func

        if logger is not None:
            self._logger = logger
        else:
            self._logger = log.NullLogger()

        if progress_handler is not None:
            self._progress_handler = progress_handler
        else:
            self._progress_handler = NullProgressHandler()

        if on_error is not None:
            self._on_error = on_error
        else:
            self._on_error = noop

    def __call__(self, entry_iter):
        """Examine a set of files for duplicate content.

        Args:
            entry_iter (iter of FileEntry): The FileEntry objects to examine.

        Yields:
            a DuplicateContentSet containing FileContent objects found to have
            identical content.
        """
        sets = self._collect_size_sets(entry_iter)
        self._logger.debug("Set count: {}", len(sets))
        for _, contents in sorted(sets, key=operator.itemgetter(0), reverse=True):
            for same_contents_set in self._search_content_in_size_set(contents):
                yield same_contents_set

    def _log_error(self, error, path=None):
        if path is None:
            self._logger.error(str(error))
        else:
            self._logger.error("{path!s}: {error!s}", path=path, error=error)

    def _collect_size_sets(self, entry_iter):
        stats = dict(files=0, errors=0)

        if self._content_key_func is None:
            indexer = AddressIgnorer()
        else:
            indexer = AddressIndexer(self._content_key_func)

        self._logger.debug("Start file enumeration")
        for entry in entry_iter:
            stats["files"] += 1
            try:
                indexer.add(entry)
            except EnvironmentError as environment_error:
                stats["errors"] += 1
                self._log_error(environment_error, entry.path)
                self._on_error(environment_error, entry.path)

        self._logger.debug(
            "End file enumeration. files={files}, errors={errors}",
            **stats
        )

        return list(indexer.sets())

    def _search_content_in_size_set(self, file_content_iter):
        stats = dict(bytes_read=0, completed=0, early_out=0, canceled=0)
        last_progress = 0

        pool = streampool.StreamPool(self._max_open_files)

        initial_set = [
            ContentStreamPair(content, pool.open(content.entry.path))
            for content in file_content_iter
        ]
        file_size = initial_set[0].content.entry.size

        current_sets = [ initial_set ]
        self._do_progress_callback(current_sets, 0, file_size)

        while len(current_sets) > 0:
            compare_set = current_sets.pop()
            assert len(compare_set) > 0, "len(compare_set) <= 0"

            if self._cancel_func is not None:
                if self._cancel_func(DuplicateContentSet._from_cs_set(compare_set)):
                    stats["canceled"] += 1
                    for cs in compare_set:
                        cs.stream.close()
                    continue

            buffers = [ ]
            next_sets = [ ]

            if file_size == 0:
                # files are zero length, so we know every one is going to result in a read
                # of b"". skip it

                # we could early-out earlier than this, but doing it here guarantees that
                # the callbacks (i.e. cancel_func, on_progress) behave consistently.
                # at least until i tidy it up further
                buffers.append(b"")
                next_sets.append(compare_set)

            elif len(compare_set) == 1:
                # in this case there is just one actual file, and we know there's more than
                # one hard/symlink to it otherwise it would've been filtered out earlier.
                # in this case, pretend we read any non-empty string (huge hack alert) and leave the set
                # unchanged.
                buffers.append(b"dummy") # big ol hack
                next_sets.append(compare_set)

            else:
                # otherwise do it properly and don't skip bits
                for cs_pair in compare_set:
                    stream = cs_pair.stream
                    try:
                        buffer = stream.read(self._buffer_size)
                        stats["bytes_read"] += len(buffer)

                    except EnvironmentError as read_error:
                        self._log_error(read_error, stream.content.entry.path)
                        self._on_error(read_error, stream.content.entry.path)
                        try:
                            stream.close()
                        except EnvironmentError as close_error:
                            self._log_error(close_error, stream.content.entry.path)
                            self._on_error(close_error, stream.content.entry.path)
                        continue

                    if stats["bytes_read"] - last_progress > PROGRESS_CALLBACK_FREQUENCY:
                        last_progress = stats["bytes_read"]
                        self._do_progress_callback([ compare_set ] + current_sets, stream.tell(), file_size)

                    try:
                        next_set = next_sets[buffers.index(buffer)]
                    except ValueError:
                        buffers.append(buffer)
                        next_set = [ ]
                        next_sets.append(next_set)

                    next_set.append(cs_pair)

            for buffer, compare_set in zip(buffers, next_sets):
                complete = len(buffer) == 0

                close_set = False
                if complete:
                    close_set = True
                    stats["completed"] += 1

                elif len(compare_set) <= 1:
                    close_set = True
                    stats["early_out"] += 1

                of_interest = (
                    (len(compare_set) >  1 and complete) or
                    (len(compare_set) == 1 and len(compare_set[0].content.entries) > 1)
                )

                if of_interest:
                    self._progress_handler.clear()
                    yield DuplicateContentSet._from_cs_set(compare_set)

                if close_set:
                    for cs in compare_set:
                        cs.stream.close()

                else:
                    current_sets.append(compare_set)

        self._do_progress_callback(current_sets, file_size, file_size)
        self._progress_handler.clear()

        self._logger.debug(
            "Content comparison end: bytes_read={bytes_read} completed={completed} early_out={early_out} canceled={canceled}",
            **stats,
        )

    def _do_progress_callback(self, cs_sets, file_pos, file_size):
        self._progress_handler.progress(
            [
                DuplicateContentSet._from_cs_set(cs)
                for cs in cs_sets
            ],
            file_pos,
            file_size,
        )


class DuplicateContentSet(tuple):
    """An immutable collection of FileContent instances.

    A DuplicateContentSet is a tuple subclass containing FileContent objects,
    with convenience methods added.
    """

    def all_entries(self):
        """Get every FileEntry object associated with every FileContent object.

        Yields:
            every FileEntry object attached to every FileContent object in the
            collection.
        """
        for content in self:
            for entry in content.entries:
                yield entry

    @property
    def content_size(self):
        """The common size of every file present in the DuplicateContentSet."""
        for entry in self.all_entries():
            return entry.size

    @property
    def total_size(self):
        """The total size on disk of the files in the DuplicateContentSet."""
        return self.content_size * len(self)

    @property
    def entry_count(self):
        """The total number of FileEntry objects in the DuplicateContentSet."""
        return sum(len(content.entries) for content in self)

    @classmethod
    def _from_cs_set(cls, cs_iter):
        return cls(cs.content for cs in cs_iter)


class NullProgressHandler(object):
    def progress(self, _sets, _file_pos, _file_size):
        pass

    def clear(self):
        pass


class AddressIndexer(object):
    def __init__(self, content_key_func):
        self._content_key_func = content_key_func
        self._size_index = collections.defaultdict(list)

    def add(self, entry):
        key = self._content_key_func(entry)
        self._size_index[entry.size].append((key, entry))

    def sets(self):
        for size, addr_entry_pairs in self._size_index.items():
            if len(addr_entry_pairs) > 1:
                yield size, list(self._collect_content(addr_entry_pairs))

    @staticmethod
    def _collect_content(addr_entry_pairs):
        addr_lookup = collections.defaultdict(list)
        for address, entry in addr_entry_pairs:
            addr_lookup[address].append(entry)
        for address, entries in addr_lookup.items():
            yield fs.FileContent(address=address, entries=entries)


class AddressIgnorer(object):
    def __init__(self):
        self._size_index = collections.defaultdict(list)

    def add(self, entry):
        self._size_index[entry.size].append(entry)

    def sets(self):
        for size, entries in self._size_index.items():
            if len(entries) > 1:
                yield size, [ fs.FileContent(address=None, entry=entry) for entry in entries ]


ContentStreamPair = collections.namedtuple(
    "ContentStreamPair", (
        "content",
        "stream",
    )
)
