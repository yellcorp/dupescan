from collections import namedtuple
import itertools
import os
import stat

from dupescan.collections import DelimitedStringSet


def cache_prop(method):
    key = method.__name__
    def wrapped_method(self):
        try:
            return self._cache[key]
        except KeyError:
            result = method(self)
            self._cache[key] = result
            return result
    return wrapped_method


# pathlib.Path is hard (impossible?) to subclass, so here's a platform-neutral
# partial re-do that also caches its result, and lets us tag it with extra info
class FileEntry(object):
    def __init__(self, path):
        self._path = path

        self._dirname = None
        self._basename = None
        self._barename = None
        self._extension = None

        self._cache = { }

    def _copy_with_path(self, path):
        return FileEntry(path)

    def _split_path(self):
        self._dirname, self._basename = os.path.split(self._path)
        self._barename, self._extension = os.path.splitext(self._basename)

    def __str__(self):
        return str(self._path)

    def __repr__(self):
        return "%s(%r)" % (
            type(self).__name__,
            self._path,
        )

    def __hash__(self):
        return hash(self._path)

    def __eq__(self, other):
        if not isinstance(other, FileEntry):
            return NotImplemented

        return self._path == other.path

    @property
    def path(self):
        return self._path

    @property
    def basename(self):
        if self._basename is None:
            self._split_path()
        return self._basename

    @property
    def barename(self):
        if self._barename is None:
            self._split_path()
        return self._barename

    @property
    def extension(self):
        if self._extension is None:
            self._split_path()
        return self._extension

    @property
    @cache_prop
    def parent(self):
        if self._dirname is None:
            self._split_path()
        return self._copy_with_path(self._dirname)

    def join(self, name):
        return self._copy_with_path(os.path.join(self._path, str(name)))

    def __truediv__(self, rhs):
        if isinstance(rhs, (str, FileEntry)):
            return self.join(rhs)
        return NotImplemented

    def __rtruediv__(self, lhs):
        if isinstance(lhs, (str, FileEntry)):
            return self._copy_with_path(
                os.path.join(str(lhs), self._path)
            )
        return NotImplemented

    @property
    @cache_prop
    def stat(self):
        return os.stat(self._path)

    @property
    @cache_prop
    def lstat(self):
        return os.lstat(self._path)

    @property
    def size(self):
        return self.stat.st_size

    @property
    def atime(self):
        return self.stat.st_atime

    @property
    def ctime(self):
        return self.stat.st_ctime

    @property
    def mtime(self):
        return self.stat.st_mtime

    @property
    def is_file(self):
        return stat.S_ISREG(self.stat.st_mode)

    @property
    def is_dir(self):
        return stat.S_ISDIR(self.stat.st_mode)

    @property
    def is_symlink(self):
        return stat.S_ISLNK(self.lstat.st_mode)


Root = namedtuple("Root", ("path", "index"))


class RootAwareFileEntry(FileEntry):
    def __init__(self, path, root=None):
        FileEntry.__init__(self, path)
        if root is not None:
            self._root = root
        else:
            self._root = Root(None, None)

    def _copy_with_path(self, path):
        return RootAwareFileEntry(path, self._root)
    
    def __repr__(self):
        return "%s(%r, %r)" % (
            type(self).__name__,
            self._path,
            self._root,
        )

    def __hash__(self):
        return (
            hash(self._path) ^
            hash(self._root)
        )

    def __eq__(self, other):
        if not isinstance(other, FileEntry):
            return NotImplemented

        return (
            self._path == other.path and
            self._root == other.root
        )

    @property
    def root(self):
        return self._root


class FileContent(object):
    __slots__ = ("address", "entries")

    def __init__(self, address, entries=None, entry=None):
        self.address = address

        entries_source = itertools.chain(
            entries if entries is not None else [ ],
            [ entry ] if entry is not None else [ ]
        )

        self.entries = tuple(entries_source)

    def __hash__(self):
        return hash(self.address) ^ hash(self.entries)

    def __eq__(self, other):
        return (
            isinstance(other, FileContent) and
            self.address == other.address and
            self.entries == other.entries
        )

    def __str__(self):
        if len(self.entries) >= 1:
            return str(self.entries[0].path)
        return ""

    def __repr__(self):
        return "%s(%r, entries=%r)" % (
            type(self).__name__,
            self.address,
            self.entries,
        )

    @property
    def entry(self):
        if len(self.entries) >= 1:
            return self.entries[0]
        return None


class MarkableFileContent(FileContent):
    __slots__ = ("marked",)

    def __init__(self, address, entries=None, entry=None, marked=None):
        super().__init__(address, entries=entries, entry=entry)
        self.marked = marked

    @classmethod
    def from_immutable(cls, file_content, marked=False):
        return cls(
            address = file_content.address,
            entries = file_content.entries,
            marked = marked,
        )

    def __hash__(self):
        return object.__hash__(self)

    def __eq__(self, other):
        return object.__eq__(self, other)

    def __repr__(self):
        return "%s(%r, %r, %r)" % (
            type(self).__name__,
            self.address,
            self.entries,
            self.marked,
        )


def catch_filter(inner_func, error_handler_func):
    if inner_func is None:
        def always_true(*args, **kwargs):
            return True
        return always_true

    def wrapped_func(*args, **kwargs):
        try:
            return inner_func(*args, **kwargs)
        except EnvironmentError as env_error:
            if error_handler_func is not None:
                error_handler_func(env_error)
            return False

    return wrapped_func


def flat_iterator(paths, dir_entry_filter=None, file_entry_filter=None, onerror=None):
    dir_entry_filter = catch_filter(dir_entry_filter, onerror)
    file_entry_filter = catch_filter(file_entry_filter, onerror)

    for index, path in enumerate(paths):
        root = Root(path, index)
        entry = RootAwareFileEntry(path, root)
        try:
            is_file = entry.is_file
        except EnvironmentError as env_error:
            onerror(env_error)
            continue

        if is_file:
            if file_entry_filter(entry):
                yield entry
        elif dir_entry_filter(entry):
            yield entry


def recurse_iterator(paths, dir_entry_filter=None, file_entry_filter=None, onerror=None):
    dir_entry_filter = catch_filter(dir_entry_filter, onerror)
    file_entry_filter = catch_filter(file_entry_filter, onerror)

    for root_index, root_path in enumerate(paths):
        root_spec = Root(root_path, root_index)
        root_entry = RootAwareFileEntry(root_path, root_spec)

        try:
            root_is_dir = root_entry.is_dir
        except EnvironmentError as env_error:
            onerror(env_error)
            continue

        filter_func = dir_entry_filter if root_is_dir else file_entry_filter
        if not filter_func(root_entry):
            continue

        if root_is_dir:
            for parent, dirs, files in os.walk(root_path, onerror):
                parent_entry = RootAwareFileEntry(parent, root_spec)
                dirs[:] = [
                    d for d in dirs
                    if dir_entry_filter(parent_entry / d)
                ]

                for f in files:
                    file_entry = parent_entry / f
                    if file_entry_filter(file_entry):
                        yield file_entry

        elif file_entry_filter(root_entry):
            yield root_entry


def unique_entries(entry_iter):
    seen = DelimitedStringSet(os.sep)
    for entry in entry_iter:
        if entry.path not in seen:
            seen.add(entry.path)
            yield entry
