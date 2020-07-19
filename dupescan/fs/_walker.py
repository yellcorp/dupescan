from typing import Iterable, Callable, Optional, Any, List, Iterator

from dupescan.fs._fileentry import FileEntry
from dupescan.fs._root import Root
from dupescan.types import AnyPath

FSPredicate = Callable[[FileEntry], bool]
ErrorHandler = Callable[[EnvironmentError], Any]


def catch_filter(inner_filter: FSPredicate, error_handler_func: ErrorHandler) -> FSPredicate:
    # If no filter function provided, return one that includes everything.  In
    # this case it will never raise an error, so error_handler_func doesn't get
    # a look-in here
    if inner_filter is None:
        def always_true(*args, **kwargs):
            return True
        return always_true

    # Otherwise if the filter function throws an EnvironmentError, pass it to
    # the error_handler_func (if provided) and return false
    def wrapped_func(*args, **kwargs):
        try:
            return inner_filter(*args, **kwargs)
        except EnvironmentError as env_error:
            if error_handler_func is not None:
                error_handler_func(env_error)
            return False

    return wrapped_func


def noerror(_):
    pass


class Walker(object):
    def __init__(
            self,
            recursive: bool,
            dir_object_filter: Optional[FSPredicate]=None,
            file_object_filter: Optional[FSPredicate]=None,
            onerror: Optional[ErrorHandler]=None
    ):
        self._recursive = bool(recursive)
        self._onerror = noerror if onerror is None else onerror
        self._dir_filter = catch_filter(dir_object_filter, self._onerror)
        self._file_filter = catch_filter(file_object_filter, self._onerror)

    def __call__(self, paths: Iterable[AnyPath]) -> Iterator[FileEntry]:
        for root_index, root_path in enumerate(paths):
            root_spec = Root(root_path, root_index)

            try:
                root_obj = FileEntry.from_path(root_path, root_spec)
            except EnvironmentError as env_error:
                self._onerror(env_error)
                continue

            if root_obj.is_dir and self._dir_filter(root_obj):
                if self._recursive:
                    yield from self._recurse_dir(root_obj)
                else:
                    yield root_obj
            elif root_obj.is_file and self._file_filter(root_obj):
                yield root_obj

    def _recurse_dir(self, root_obj: FileEntry):
        dir_obj_q: List[FileEntry] = [ root_obj ]
        next_dirs: List[FileEntry] = [ ]

        while len(dir_obj_q) > 0:
            dir_obj = dir_obj_q.pop()
            next_dirs.clear()

            try:
                for child_obj in dir_obj.dir_content():
                    try:
                        if (
                            child_obj.is_dir and
                            not child_obj.is_symlink and
                            self._dir_filter(child_obj)
                        ):
                            next_dirs.append(child_obj)
                        
                        elif (
                            child_obj.is_file and
                            self._file_filter(child_obj)
                        ):
                            yield child_obj
                    except EnvironmentError as query_error:
                        self._onerror(query_error)
            except EnvironmentError as env_error:
                self._onerror(env_error)

            dir_obj_q.extend(reversed(next_dirs))


def flat_iterator(
        paths: Iterable[AnyPath],
        dir_object_filter: Optional[FSPredicate]=None,
        file_object_filter: Optional[FSPredicate]=None,
        onerror: Optional[ErrorHandler]=None
) -> Iterator[FileEntry]:
    return Walker(False, dir_object_filter, file_object_filter, onerror)(paths)


def recurse_iterator(
        paths: Iterable[AnyPath],
        dir_object_filter: Optional[FSPredicate]=None,
        file_object_filter: Optional[FSPredicate]=None,
        onerror: Optional[ErrorHandler]=None
) -> Iterator[FileEntry]:
    return Walker(True, dir_object_filter, file_object_filter, onerror)(paths)
