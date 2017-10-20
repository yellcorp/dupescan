import atexit
import collections
import math
import os
import sqlite3
import sys
import tempfile

from dupescan import (
    fs,
    log,
    platform,
    streampool,
)


__all__ = (
    "DuplicateFinder",
    "DuplicateInstanceSet",
)


def noop(*args, **kwargs):
    pass


def nearest_pow2(n):
    if n < 1:
        return 1
    return 2 ** int(math.log(n, 2) + 0.5)


# invoke walk callback after enumerating this many files
WALK_CALLBACK_FREQUENCY = 2000

# invoke compare callback after reading this many bytes from the filesystem
COMPARE_CALLBACK_FREQUENCY = 0x100000

class DuplicateFinder(object):
    """Main class for detecting files with duplicate content in a set.

    After creating an instance of DuplicateFinder, use it like a function,
    passing to it a single argument - an iterator of FileEntry objects. It will
    yield a `DuplicateInstanceSet` for every set of files it discovers having
    the same content.
    """
    def __init__(
        self,
        max_open_files = None,
        max_memory = None,
        max_buffer_size = None,
        cancel_func = None,
        logger = None,
        compare_progress_handler = None,
        walk_progress_handler = None,
        on_error = None, # TODO: name this consistently
    ):
        """Construct a new DuplicateFinder.

        Arguments:
            max_open_files (int or None): Sets the maximum number of files to
                be opened when reading from potentially duplicate files. If a
                potential set contains more files than this number, older
                filehandles will be closed before newer ones are opened.

            max_memory (int or None): Sets the maximum amount of memory (in
                bytes) to use when comparing files.

            max_buffer_size (int or None): Sets the maximum buffer size when
                comparing files.

            cancel_func (func or None): A function that can cancel a file
                comparison operation by returning True. It takes a single
                DuplicateInstanceSet argument and returns a bool.  It is called
                every `buffer_size` bytes (including before the first read),
                with a DuplicateInstanceSet containing FileInstance objects
                that are all, thus far, identical in content.

            logger (log.Logger or None): A logger object used to print debug
                information.

            compare_progress_handler (CompareProgressHandler or None): A
                CompareProgressHandler for reporting content compare progress.
                A CompareProgressHandler is an object that has two methods:
                `progress(sets, bytes_read, bytes_total)` and `clear()`.
                `progress` will be called periodically during file reads.
                `sets` will be a list of DuplicateInstanceSet objects,
                reflecting the current state of the compare operation.
                `bytes_read` is the number of bytes read from a single
                representative file, and `bytes_total` is the file size.
                `clear` will be called immediately before any event that may
                cause other output to be printed.

            walk_progress_handler (WalkProgressHandler or None): A
                WalkProgressHandler for reporting file enumeration progress. A
                WalkProgressHandler has two methods: `progress(path)` and
                `complete()`. `progress` will be called periodically during
                enumeration of the filesystem. `path` will be a string
                representing the last path to be sen. `complete` will be called
                when enumeration is complete.

            on_error (func or None): A function accepting 2 arguments:
                `error` and `path`, called whenever an error is encountered.
                `error` is an instance of EnvironmentError or one of its
                subclasses. `path` is the path involved. To propagate the
                error, reraise it from within this function. If None is
                specified, errors are ignored. In any case, the error and path
                are first sent to the `logger`.
        """

        if max_open_files is not None and max_open_files >= 1:
            self._max_open_files = max_open_files
        else:
            self._max_open_files = platform.decide_max_open_files()

        if max_memory is not None and max_memory >= 1:
            self._max_memory = max_memory
        else:
            self._max_memory = platform.DEFAULT_MAX_MEMORY

        if max_buffer_size is not None and max_buffer_size >= 1:
            self._max_buffer_size = max_buffer_size
        else:
            self._max_buffer_size = platform.DEFAULT_MAX_BUFFER_SIZE

        self._cancel_func = cancel_func

        if logger is not None:
            self._logger = logger
        else:
            self._logger = log.NullLogger()

        if compare_progress_handler is not None:
            self._compare_progress_handler = compare_progress_handler
        else:
            self._compare_progress_handler = NullCompareProgressHandler()

        if walk_progress_handler is not None:
            self._walk_progress_handler = walk_progress_handler
        else:
            self._walk_progress_handler = NullWalkProgressHandler()

        if on_error is not None:
            self._on_error = on_error
        else:
            self._on_error = noop

    def __call__(self, entries):
        """Examine a set of files for duplicate content.

        Args:
            entries (iter of FileEntry): The FileEntry objects to examine.

        Yields:
            a DuplicateInstanceSet containing FileInstance objects found to
            have identical content.
        """
        for _size, instances in self._collect_size_sets(entries):
            for dupe_set in self._compare_content_in_size_set(instances):
                yield dupe_set

    def _log_error(self, error, path=None):
        if path is None:
            self._logger.error(str(error))
        else:
            self._logger.error("{path!s}: {error!s}", path=path, error=error)

    def _collect_size_sets(self, entries):
        stats = dict(files=0, errors=0)
        last_files_callback = -WALK_CALLBACK_FREQUENCY

        indexer = DatabaseIndexer()

        self._logger.debug("Start file enumeration")
        for entry in entries:
            stats["files"] += 1
            if stats["files"] - last_files_callback >= WALK_CALLBACK_FREQUENCY:
                self._walk_progress_handler.progress(entry.path)
                last_files_callback = stats["files"]

            try:
                indexer.add(entry)
            except EnvironmentError as environment_error:
                stats["errors"] += 1
                self._log_error(environment_error, entry.path)
                self._on_error(environment_error, entry.path)

        self._walk_progress_handler.complete()
        self._logger.debug(
            "End file enumeration. files={files}, errors={errors}",
            **stats
        )

        indexer.end()

        return indexer.sets()

    def _compare_content_in_size_set(self, instance_iter):
        stats = dict(bytes_read=0, completed=0, early_out=0, canceled=0)
        last_progress = 0

        pool = streampool.StreamPool(self._max_open_files)

        initial_set = [
            InstanceStreamPair(instance, pool.open(instance.entry.path))
            for instance in instance_iter
        ]
        file_size = initial_set[0].instance.entry.size

        current_sets = [ initial_set ]
        self._do_compare_progress_callback(current_sets, 0, file_size)

        first = True
        while len(current_sets) > 0:
            compare_set = current_sets.pop()
            assert len(compare_set) > 0, "len(compare_set) <= 0"

            if self._cancel_func is not None:
                if self._cancel_func(DuplicateInstanceSet._from_is_pairs(compare_set)):
                    stats["canceled"] += 1
                    for cs in compare_set:
                        cs.stream.close()
                    continue

            buffers = [ ]
            next_sets = [ ]

            if file_size == 0:
                # files are zero length, so we know every one is going to
                # result in a read of b"". skip it

                # we could early-out earlier than this, but doing it here
                # guarantees that the callbacks (i.e. cancel_func, on_progress)
                # behave consistently.  at least until i tidy it up further
                buffers.append(b"")
                next_sets.append(compare_set)

            elif len(compare_set) == 1:
                # in this case there is just one actual file, and we know
                # there's more than one hard/symlink to it otherwise it
                # would've been filtered out earlier.  in this case, pretend we
                # read any non-empty string (huge hack alert) and leave the set
                # unchanged.
                buffers.append(b"dummy") # big ol hack
                next_sets.append(compare_set)

            else:
                # otherwise do it properly and don't skip bits

                if first:
                    buffer_size = platform.MIN_BUFFER_SIZE
                    first = False
                else:
                    buffer_size = max(
                        platform.MIN_BUFFER_SIZE,
                        min(
                            self._max_buffer_size,
                            nearest_pow2(self._max_memory / len(compare_set))
                        )
                    )

                pool.max_open_files = max(
                    1,
                    min(
                        self._max_open_files,
                        int(self._max_memory / buffer_size)
                    )
                )

                for cs_pair in compare_set:
                    stream = cs_pair.stream
                    try:
                        buffer = stream.read(buffer_size)
                        stats["bytes_read"] += len(buffer)

                    except EnvironmentError as read_error:
                        self._log_error(read_error, stream.instance.entry.path)
                        self._on_error(read_error, stream.instance.entry.path)
                        try:
                            stream.close()
                        except EnvironmentError as close_error:
                            self._log_error(close_error, stream.instance.entry.path)
                            self._on_error(close_error, stream.instance.entry.path)
                        continue

                    if stats["bytes_read"] - last_progress > COMPARE_CALLBACK_FREQUENCY:
                        last_progress = stats["bytes_read"]
                        self._do_compare_progress_callback([ compare_set ] + current_sets, stream.tell(), file_size)

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
                    (len(compare_set) == 1 and len(compare_set[0].instance.entries) > 1)
                )

                if of_interest:
                    self._compare_progress_handler.clear()
                    yield DuplicateInstanceSet._from_is_pairs(compare_set)

                if close_set:
                    for cs in compare_set:
                        cs.stream.close()

                else:
                    current_sets.append(compare_set)

        self._do_compare_progress_callback(current_sets, file_size, file_size)
        self._compare_progress_handler.clear()

        self._logger.debug(
            "Content comparison end: bytes_read={bytes_read} completed={completed} early_out={early_out} canceled={canceled}",
            **stats,
        )

    def _do_compare_progress_callback(self, cs_sets, file_pos, file_size):
        self._compare_progress_handler.progress(
            [
                DuplicateInstanceSet._from_is_pairs(cs)
                for cs in cs_sets
            ],
            file_pos,
            file_size,
        )


class DuplicateInstanceSet(tuple):
    """An immutable collection of FileInstance instances.

    A DuplicateInstanceSet is a tuple subclass containing FileInstance objects,
    with convenience methods added.
    """

    def all_entries(self):
        """Get every FileEntry object associated with every FileInstance
        object.

        Yields:
            every FileEntry object attached to every FileInstance object in the
            collection.
        """
        for instance in self:
            for entry in instance.entries:
                yield entry

    @property
    def instance_size(self):
        """The common size of every file present in the DuplicateInstanceSet."""
        for entry in self.all_entries():
            return entry.size

    @property
    def total_size(self):
        """The total size on disk of the files in the DuplicateInstanceSet."""
        return self.instance_size * len(self)

    @property
    def entry_count(self):
        """The total number of FileEntry objects in the DuplicateInstanceSet."""
        return sum(len(instance.entries) for instance in self)

    @classmethod
    def _from_is_pairs(cls, is_iter):
        return cls(is_pair.instance for is_pair in is_iter)


class NullCompareProgressHandler(object):
    def progress(self, _sets, _file_pos, _file_size):
        pass

    def clear(self):
        pass


class NullWalkProgressHandler(object):
    def progress(self, _path):
        pass

    def complete(self):
        pass


def fetch_iterator(sqlite_cursor):
    while True:
        chunk = sqlite_cursor.fetchmany()
        if len(chunk) > 0:
            for row in chunk:
                yield row
        else:
            break


DB_COMMIT_FREQ = 0x4000
class DatabaseIndexer(object):
    def __init__(self):
        self._dir = tempfile.mkdtemp()
        self._path = os.path.join(self._dir, "dupescanindex")
        atexit.register(self.dispose)

        self._counter = 0 
        self._conn = sqlite3.connect(self._path)

        cursor = self._conn.cursor()

        cursor.execute("""\
            create table files (
                size integer,
                path text unique on conflict ignore,
                rootn integer
            )
        """)

        cursor.execute("""\
            create index size_index on files (size)
        """)

        cursor.execute("""\
            create unique index path_index on files (path)
        """)

        cursor.execute("""\
            create table roots (
                rootn integer primary key on conflict ignore,
                path text
            )
        """)

        cursor.close()
        self._conn.commit()

    def dispose(self):
        if self._path is None:
            return

        self._conn.commit()
        self._conn.close()
        self._conn = None

        path = self._path
        self._path = None

        try:
            os.remove(path)
            os.rmdir(self._dir)
        except OSError as os_error:
            print(str(os_error), file=sys.stderr)

    def __del__(self):
        self.dispose()

    def add(self, entry):
        cursor = self._conn.cursor()
        
        if entry.root.index is not None:
            cursor.execute("""\
                insert into roots values (?,?)
            """, (entry.root.index, entry.root.path))

        cursor.execute("""\
            insert into files values (?,?,?)
        """, (entry.size, entry.path, entry.root.index))
        
        self._counter += 1
        if self._counter >= DB_COMMIT_FREQ:
            self.end()

    def end(self):
        self._counter = 0
        self._conn.commit()

    def sets(self):
        self.end()

        unique_cursor = self._conn.cursor()
        unique_cursor.execute("""\
            select size, count(*) from files
            group by size
            having count(*) > 1
        """)

        for size, _count in fetch_iterator(unique_cursor):
            set_cursor = self._conn.cursor()
            set_cursor.execute("""\
                select
                    files.path,
                    files.rootn,
                    roots.path
                from files left join roots using (rootn)
                where files.size = ?
            """, (size,))

            entries = [
                fs.FileEntry.from_path(path, fs.Root(root_path, root_index))
                for (path, root_index, root_path) in set_cursor.fetchall()
            ]

            set_cursor.close()

            yield size, list(fs.FileInstance.group_entries_by_identifier(entries))

        unique_cursor.close()


InstanceStreamPair = collections.namedtuple(
    "InstanceStreamPair", (
        "instance",
        "stream",
    )
)
