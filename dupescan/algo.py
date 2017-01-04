from .fs import FileInstance, AnonymousStorageId, UnixStorageId
from .resources import StreamPool, decide_max_open_files

import collections
import operator
import os
import sys


def file_error_ignore(path, error):
    pass

def file_error_print_stderr(path, error):
    print("{0!s}: {1!s}".format(path, error), file=sys.stderr)

def file_error_raise(path, error):
    raise error

FILE_ERROR_HANDLERS = {
    "ignore":       file_error_ignore,
    "print_stderr": file_error_print_stderr,
    "raise":        file_error_raise
}


def log_ignore(message):
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


def find_duplicate_files_by_content(file_instance_list, max_open_files, buffer_size, error_cb, log_cb):
    pool = StreamPool(max_open_files)

    completed = 0
    aborted = 0

    initial_set = [ ]
    stream_to_instance = { }
    for instance in file_instance_list:
        stream = pool.open(instance.path())
        initial_set.append(stream)
        stream_to_instance[stream] = instance

    current_sets = [ initial_set ]

    while len(current_sets) > 0:
        compare_set = current_sets.pop()
        new_chunks = [ ]
        new_sets = [ ]

        for stream in compare_set:
            try:
                chunk = stream.read(buffer_size)
            except EnvironmentError as read_error:
                error_path = stream.path
                error_cb(error_path, read_error)
                try:
                    stream.close()
                except EnvironmentError as close_error:
                    error_cb(error_path, close_error)
                continue

            try:
                new_set_index = new_chunks.index(chunk)
                new_sets[new_set_index].append(stream)
            except ValueError:
                new_chunks.append(chunk)
                new_sets.append([ stream ])

        for chunk, stream_set in zip(new_chunks, new_sets):
            complete = len(chunk) == 0

            discard = False
            if complete:
                discard = True
                completed += 1

            elif len(stream_set) < 2:
                discard = True
                aborted += 1

            of_interest = (
                (complete and len(stream_set) > 1) or
                (len(stream_set) == 1 and len(stream_to_instance[stream_set[0]].paths) > 1)
            )

            if of_interest:
                yield tuple(stream_to_instance[stream] for stream in stream_set)

            if discard:
                for stream in stream_set:
                    stream.close()
            else:
                current_sets.append(stream_set)

    log_cb("Content comparison end: completed={0} aborted={1}".format(completed, aborted))


def enumerate_files(
    path_iterator,
    identify_instance,
    error_cb,
    log_cb,
):
    size_index = collections.defaultdict(list)
    file_count = 0
    error_count = 0

    log_cb("Start file enumeration")
    for path in path_iterator:
        file_count += 1
        try:
            stat = os.stat(path)
            storage_id = identify_instance(path, stat)
            size_index[stat.st_size].append((storage_id, path))
        except EnvironmentError as ee:
            error_count += 1
            error_cb(path, ee)
    log_cb("End file enumeration. file_count={0}, error_count={1}".format(file_count, error_count))
    log_cb("Unique sizes: {0}".format(len(size_index)))

    return [
        (size, to_multimap(id_path_pairs))
        for size, id_path_pairs in size_index.items()
        if len(id_path_pairs) > 1
    ]


DEFAULT_BUFFER_SIZE = 4096
def find_duplicate_files(
    path_iterator,
    collect_inodes=None,
    max_open_files=None,
    error_cb=None,
    log_cb=None,
    buffer_size=None
):
    error_cb = resolve_handler(error_cb, "ignore", FILE_ERROR_HANDLERS)
    log_cb =   resolve_handler(log_cb,   "ignore", LOG_HANDLERS)

    if collect_inodes:
        get_id = UnixStorageId.from_path_stat # TODO: figure out equivalent for windows
    else:
        get_id = AnonymousStorageId.from_path_stat

    sets = enumerate_files(path_iterator, get_id, error_cb, log_cb)
    log_cb("Set count: {0}".format(len(sets)))

    if max_open_files is None or max_open_files <= 0:
        max_open_files = decide_max_open_files()

    if buffer_size is None or buffer_size <= 0:
        buffer_size = DEFAULT_BUFFER_SIZE

    for size, id_index in sorted(sets, key=operator.itemgetter(0), reverse=True):
        instances = [
            FileInstance(storage_id=storage_id, paths=paths)
            for storage_id, paths in id_index.items()
        ]

        if size == 0:
            log_cb("Skipping content comparison due to zero length")
            yield tuple(instances)

        elif len(instances) == 1:
            log_cb("Skipping content comparison due to single instance")
            yield tuple(instances)

        else:
            log_cb("Content comparison start: {0} instances of {1} bytes each".format(len(instances), size))
            for same_contents_set in find_duplicate_files_by_content(instances, max_open_files, buffer_size, error_cb, log_cb):
                yield same_contents_set
