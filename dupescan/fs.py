import itertools
import os
import stat

from dupescan import util


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
    def __init__(self, path, root=None, root_index=None):
        self._path = path
        self._root = root
        self._root_index = root_index

        self._dirname = None
        self._basename = None
        self._barename = None
        self._extension = None

        self._cache = { }

    def _copy_with_path(self, path):
        return FileEntry(path, self._root, self._root_index)

    def _split_path(self):
        self._dirname, self._basename = os.path.split(self._path)
        self._barename, self._extension = os.path.splitext(self._basename)

    def __str__(self):
        return str(self._path)

    def __repr__(self):
        return "%s(%r, %r, %r)" % (
            type(self).__name__,
            self._path,
            self._root,
            self._root_index
        )

    @property
    def path(self):
        return self._path

    @property
    def root(self):
        return self._root

    @property
    def root_index(self):
        return self._root_index

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
        return stat.S_ISLNK(self.stat.st_mode)


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
        return "FileInstance(%r, entries=%r)" % (self.address, self.entries)

    @property
    def entry(self):
        if len(self.entries) >= 1:
            return self.entries[0]
        return None


def posix_address(entry):
    entry_stat = entry.stat
    return (entry_stat.st_dev, entry_stat.st_ino)


# TODO
# def windows_address_getter():


def flat_iterator(paths, dir_entry_filter=None, file_entry_filter=None):
    if dir_entry_filter is None:
        dir_entry_filter = lambda _: True

    if file_entry_filter is None:
        file_entry_filter = lambda _: True

    for index, path in enumerate(paths):
        entry = FileEntry(path, path, index)
        if entry.is_file:
            if file_entry_filter(entry):
                yield entry
        elif dir_entry_filter(entry):
            yield entry


def recurse_iterator(paths, dir_entry_filter=None, file_entry_filter=None):
    if file_entry_filter is None:
        file_entry_filter = lambda _: True

    for root_index, root in enumerate(paths):
        root_entry = FileEntry(root, root, root_index)
        if root_entry.is_dir:
            for parent, dirs, files in os.walk(root):
                parent_entry = FileEntry(parent, root, root_index)
                if dir_entry_filter:
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
    seen = util.DelimitedStringSet(os.sep)
    for entry in entry_iter:
        if entry.path not in seen:
            seen.add(entry.path)
            yield entry
