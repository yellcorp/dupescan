from .fs import FileContent, posix_address
from .resources import StreamPool, decide_max_open_files

import collections
import operator
import sys


def file_error_ignore(_path, _error):
    pass

def file_error_print_stderr(path, error):
    print("{0!s}: {1!s}".format(path, error), file=sys.stderr)

def file_error_raise(_path, error):
    raise error

FILE_ERROR_HANDLERS = {
    "ignore":       file_error_ignore,
    "print_stderr": file_error_print_stderr,
    "raise":        file_error_raise
}


def log_ignore(_message):
    pass

def log_print_stderr(message):
    print(message, file=sys.stderr)

LOG_HANDLERS = {
    "ignore":       log_ignore,
    "print_stderr": log_print_stderr,
}


def to_multimap(pairs):
    result = collections.defaultdict(list)
    for key, value in pairs:
        result[key].append(value)
    return result


def resolve_handler(value, default, lookup):
    if value is None:
        value = default

    if isinstance(value, str):
        return lookup[value]

    return value


ContentStreamPair = collections.namedtuple(
    "ContentStreamPair", (
        "content",
        "stream",
    )
)


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


# TODO: cancel_func can, for example, cancel a comparison if all content.entries[].root_index are identical
# because something i've wanted to do is compare only between roots, not within them
def find_duplicate_content_in_size_set(file_content_list, max_open_files, buffer_size, error_cb, log_cb, cancel_func=None):
    completed = 0
    early_out = 0
    canceled = 0

    pool = StreamPool(max_open_files)

    initial_set = [
        ContentStreamPair(content, pool.open(content.entry.path))
        for content in file_content_list
    ]

    current_sets = [ initial_set ]

    while len(current_sets) > 0:
        compare_set = current_sets.pop()

        cancel = False
        if cancel_func is not None:
            cancel = cancel_func(DuplicateContentSet._from_cs_set(compare_set))

        if cancel:
            canceled += 1
            for cs in compare_set:
                cs.stream.close()
            continue

        buffers = [ ]
        next_sets = [ ]

        for cs_pair in compare_set:
            stream = cs_pair.stream
            try:
                buffer = stream.read(buffer_size)
            except EnvironmentError as read_error:
                error_path = stream.entry
                error_cb(error_path, read_error)
                try:
                    stream.close()
                except EnvironmentError as close_error:
                    error_cb(error_path, close_error)
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
                completed += 1

            elif len(compare_set) <= 1:
                close_set = True
                early_out += 1

            of_interest = (
                not cancel and (
                    (len(compare_set) >  1 and complete) or
                    (len(compare_set) == 1 and len(compare_set[0].content.entries) > 1)
                )
            )

            if of_interest:
                yield DuplicateContentSet._from_cs_set(compare_set)

            if close_set:
                for cs in compare_set:
                    cs.stream.close()

            else:
                current_sets.append(compare_set)

    log_cb("Content comparison end: completed=%d early_out=%d canceled=%d" % (completed, early_out, canceled))


class AddressIndexer(object):
    def __init__(self, address_func):
        self._address_func = address_func
        self._size_index = collections.defaultdict(list)

    def add(self, entry):
        address = self._address_func(entry)
        self._size_index[entry.size].append((address, entry))

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


def collect_size_sets(
    entry_iterator,
    address_func,
    error_cb,
    log_cb,
):
    size_index = collections.defaultdict(list)
    file_count = 0
    error_count = 0

    if address_func is None:
        indexer = AddressIgnorer()
    else:
        indexer = AddressIndexer(address_func)

    log_cb("Start file enumeration")
    for entry in entry_iterator:
        file_count += 1
        try:
            indexer.add(entry)
        except EnvironmentError as ee:
            error_count += 1
            error_cb(entry.path, ee)
    log_cb("End file enumeration. file_count={0}, error_count={1}".format(file_count, error_count))
    log_cb("Unique sizes: {0}".format(len(size_index)))

    return list(indexer.sets())


DEFAULT_BUFFER_SIZE = 4096
def find_duplicate_files(
    entry_iterator,
    collect_inodes=None,
    max_open_files=None,
    error_cb=None,
    log_cb=None,
    buffer_size=None
):
    error_cb = resolve_handler(error_cb, "ignore", FILE_ERROR_HANDLERS)
    log_cb =   resolve_handler(log_cb,   "ignore", LOG_HANDLERS)

    if collect_inodes:
        get_id = posix_address # TODO: figure out equivalent for windows
    else:
        get_id = None

    sets = collect_size_sets(entry_iterator, get_id, error_cb, log_cb)
    log_cb("Set count: {0}".format(len(sets)))

    if max_open_files is None or max_open_files <= 0:
        max_open_files = decide_max_open_files()

    if buffer_size is None or buffer_size <= 0:
        buffer_size = DEFAULT_BUFFER_SIZE

    for size, contents in sorted(sets, key=operator.itemgetter(0), reverse=True):
        # todo: for cancel_func to behave consistently, we will have to move these early-outs
        # into find_duplicate_content_in_size_set
        if size == 0:
            log_cb("Skipping content comparison due to zero length")
            yield DuplicateContentSet(contents)

        elif len(contents) == 1:
            log_cb("Skipping content comparison due to single instance")
            yield DuplicateContentSet(contents)

        else:
            log_cb("Content comparison start: {0} instances of {1} bytes each".format(len(contents), size))
            for same_contents_set in find_duplicate_content_in_size_set(contents, max_open_files, buffer_size, error_cb, log_cb):
                yield same_contents_set
