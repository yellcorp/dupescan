import os
import stat
from typing import Union, Optional, AnyStr, Iterator

from ._root import NO_ROOT, Root
from ..types import AnyPath


class PathAdapter(object):
    """A recreation of os.DirEntry which can be constructed from a path"""
    def __init__(self, path):
        if isinstance(path, (bytes, str, os.PathLike)):
            self.path = os.fspath(path)
            self.dirname, self.name = os.path.split(self.path)
        else:
            self.dirname, self.name = path
            self.path = os.path.join(self.dirname, self.name)

        self._stat = { }

    def __str__(self):
        return str(self.path)

    def __repr__(self):
        return "%s(%r)" % (type(self).__name__, self.path)

    def __fspath__(self):
        return self.path

    def inode(self):
        return self.stat(follow_symlinks=False).st_ino

    def is_dir(self, *, follow_symlinks=True):
        return stat.S_ISDIR(self.stat(follow_symlinks=follow_symlinks).st_mode)

    def is_file(self, *, follow_symlinks=True):
        return stat.S_ISREG(self.stat(follow_symlinks=follow_symlinks).st_mode)

    def is_symlink(self):
        return stat.S_ISLNK(self.stat(follow_symlinks=False).st_mode)

    def stat(self, *, follow_symlinks=True):
        follow = bool(follow_symlinks)
        if follow in self._stat:
            return self._stat[follow]
        
        result = os.stat(self.path, follow_symlinks=follow)
        self._stat[follow] = result
        return result


DirEntryLike = Union[os.DirEntry, PathAdapter]


# Like pathlib.Path, but because the needs of this app are a little beyond what
# it provides, and it's hard (impossible?) to subclass, this is a partial
# rewrite of what we need with extra bits added on. It benefits from the
# caching behavior that os.DirEntry offers, and can use one as a delegate.
# Otherwise it can be constructed with a plain old path as well. Use the
# classmethods from_* to create instances.
class FileEntry(os.PathLike):
    def __init__(self, dirname: AnyPath, resource: DirEntryLike, root=NO_ROOT):
        if not isinstance(resource, (os.DirEntry, PathAdapter)):
            raise TypeError("resource must be an instance of os.DirEntry or PathAdapter")

        self._dirname = os.fspath(dirname)
        self._resource = resource

        self._splitext: Optional[AnyStr] = None
        self._root: Root = NO_ROOT if root is None else root
        self._parent: Optional['FileEntry'] = None

    def __str__(self) -> str:
        return str(self._resource.path)

    def __repr__(self) -> str:
        return "%s(%r, %r, %r)" % (
            type(self).__name__,
            self._dirname,
            self._resource,
            self._root
        )

    def __fspath__(self) -> AnyStr:
        return self._resource.path

    def __hash__(self):
        return (
            hash(self._dirname) ^
            hash(self._resource) ^
            hash(self._root)
        )

    def __eq__(self, other) -> bool:
        if not isinstance(other, FileEntry):
            return NotImplemented

        return (
            self._dirname == other._dirname and
            self._resource == other._resource and
            self._root == other._root
        )

    def _copy_with_path(self, path) -> 'FileEntry':
        return FileEntry.from_path(path, self._root)

    @classmethod
    def from_path(cls, path, root=NO_ROOT) -> 'FileEntry':
        resource = PathAdapter(path)
        return cls(resource.dirname, resource, root)

    @classmethod
    def from_dir_and_name(cls, parent, name, root=NO_ROOT) -> 'FileEntry':
        return cls(parent, PathAdapter((parent, name)), root)

    @classmethod
    def from_dir_entry(cls, parent, entry, root=NO_ROOT) -> 'FileEntry':
        return cls(parent, entry, root)

    @property
    def path(self) -> AnyStr:
        return self._resource.path

    @property
    def root(self) -> Root:
        return self._root

    @property
    def parent(self) -> 'FileEntry':
        if self._parent is None:
            self._parent = self._copy_with_path(self._dirname)
        return self._parent

    def join(self, name: AnyPath) -> 'FileEntry':
        name = os.fspath(name)

        joined = self._copy_with_path(os.path.join(self._resource.path, name))

        if (
            name != os.curdir and
            name != os.pardir and
            os.sep not in name and (
                os.altsep is None or
                os.altsep not in name
            )
        ):
            joined._parent = self
        return joined

    def dir_content(self) -> Iterator['FileEntry']:
        with os.scandir(self._resource.path) as entries:
            for entry in entries:
                child_obj = FileEntry.from_dir_entry(
                    self._resource.path,
                    entry,
                    self._root
                )
                child_obj._parent = self
                yield child_obj

    def __truediv__(self, rhs) -> 'FileEntry':
        if isinstance(rhs, (str, bytes, os.PathLike)):
            return self.join(rhs)
        return NotImplemented

    def __rtruediv__(self, lhs) -> 'FileEntry':
        return self._copy_with_path(os.path.join(os.fspath(lhs), self._resource.path))

    @property
    def basename(self) -> AnyStr:
        return self._resource.name

    @property
    def dirname(self) -> AnyStr:
        return self._dirname

    @property
    def barename(self) -> AnyStr:
        if self._splitext is None:
            self._splitext = os.path.splitext(self._resource.name)
        return self._splitext[0]
    
    @property
    def extension(self) -> AnyStr:
        if self._splitext is None:
            self._splitext = os.path.splitext(self._resource.name)
        return self._splitext[1]

    @property
    def stat(self) -> os.stat_result:
        return self._resource.stat()

    @property
    def size(self):
        return self.stat.st_size

    @property
    def atime(self):
        return self._resource.stat().st_atime

    @property
    def ctime(self):
        return self._resource.stat().st_ctime

    @property
    def mtime(self):
        return self._resource.stat().st_mtime

    @property
    def is_file(self) -> bool:
        return self._resource.is_file()

    @property
    def is_dir(self) -> bool:
        return self._resource.is_dir()

    @property
    def is_symlink(self) -> bool:
        return self._resource.is_symlink()

    @property
    def inode(self):
        return self._resource.inode()

    @property
    def dev(self):
        return self._resource.stat(follow_symlinks=False).st_dev

    @property
    def uid(self):
        inode = self._resource.inode()
        dev = self._resource.stat(follow_symlinks=False).st_dev

        # quirk: per documentation, on windows, the stat returned from os.DirEntry.stat() has 
        # st_ino and st_dev set to 0
        if inode == 0 or dev == 0:
            current_stat = os.stat(self._resource.path, follow_symlinks=False)
            inode = current_stat.st_ino
            dev = current_stat.st_dev

        return dev, inode
