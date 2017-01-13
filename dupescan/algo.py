import collections
import operator

from dupescan.fs import FileContent
from dupescan.log import NullLogger
from dupescan.platform import decide_max_open_files
from dupescan.streampool import StreamPool


__all__ = (
    "DEFAULT_BUFFER_SIZE",
    "DuplicateFinder",
    "DuplicateContentSet",
)


def noop(*args, **kwargs):
    pass


DEFAULT_BUFFER_SIZE = 4096
class DuplicateFinder(object):
    def __init__(
        self,
        content_key_func = None,
        max_open_files = None,
        buffer_size = None,
        cancel_func = None,
        logger = None,
        on_error = None,
    ):
        self._content_key_func = content_key_func

        if max_open_files is not None and max_open_files >= 1:
            self._max_open_files = max_open_files
        else:
            self._max_open_files = decide_max_open_files()

        if buffer_size is not None and buffer_size >= 1:
            self._buffer_size = buffer_size
        else:
            self._buffer_size = DEFAULT_BUFFER_SIZE

        self._cancel_func = cancel_func

        if logger is not None:
            self._logger = logger
        else:
            self._logger = NullLogger()

        if on_error is not None:
            self._on_error = on_error
        else:
            self._on_error = noop

    def __call__(self, entry_iter):
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
        stats = dict(completed=0, early_out=0, canceled=0)

        pool = StreamPool(self._max_open_files)

        initial_set = [
            ContentStreamPair(content, pool.open(content.entry.path))
            for content in file_content_iter
        ]

        current_sets = [ initial_set ]

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

            if compare_set[0].content.entry.size == 0:
                # files are zero length, so we know every one is going to result in a read
                # of b"". skip it
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
                    except EnvironmentError as read_error:
                        self._log_error(read_error, stream.content.entry.path)
                        self._on_error(read_error, stream.content.entry.path)
                        try:
                            stream.close()
                        except EnvironmentError as close_error:
                            self._log_error(close_error, stream.content.entry.path)
                            self._on_error(close_error, stream.content.entry.path)
                        continue

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
                    yield DuplicateContentSet._from_cs_set(compare_set)

                if close_set:
                    for cs in compare_set:
                        cs.stream.close()

                else:
                    current_sets.append(compare_set)

        self._logger.debug(
            "Content comparison end: completed={completed} early_out={early_out} canceled={canceled}",
            **stats,
        )


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
            yield FileContent(address=address, entries=entries)


class AddressIgnorer(object):
    def __init__(self):
        self._size_index = collections.defaultdict(list)

    def add(self, entry):
        self._size_index[entry.size].append(entry)

    def sets(self):
        for size, entries in self._size_index.items():
            if len(entries) > 1:
                yield size, [ FileContent(address=None, entry=entry) for entry in entries ]


class DuplicateContentSet(tuple):
    def all_entries(self):
        for content in self:
            for entry in content.entries:
                yield entry

    @property
    def content_size(self):
        for entry in self.all_entries():
            return entry.size

    @property
    def total_size(self):
        return self.content_size * len(self)

    @property
    def entry_count(self):
        return sum(len(content.entries) for content in self)

    @classmethod
    def _from_cs_set(cls, cs_iter):
        return cls(cs.content for cs in cs_iter)


ContentStreamPair = collections.namedtuple(
    "ContentStreamPair", (
        "content",
        "stream",
    )
)
