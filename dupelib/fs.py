import itertools


class FileInstance(object):
    def __init__(self, storage_id=None, path=None, paths=None):
        if paths is not None and path is None:
            self.paths = tuple(paths)
        elif path is not None and paths is None:
            self.paths = (path,)
        else:
            raise ValueError("Specify exactly one of either path or paths")

        self.storage_id = storage_id

    def __hash__(self):
        return hash(self.paths) ^ hash(self.storage_id)

    def __eq__(self, other):
        return (
            isinstance(other, FileInstance) and
            self.paths == other.paths and
            self.storage_id == other.storage_id
        )

    def __str__(self):
        return self.path()

    def __repr__(self):
        return "FileInstance({0!r}, paths={1!r})".format(self.storage_id, self.paths)

    def path(self):
        return self.paths[0]


class AnonymousStorageId(object):
    _counter = itertools.count(0)

    def __init__(self):
        self.number = next(self._counter)

    def presentation_string(self):
        return None

    def __str__(self):
        return "<AnonymousStorageId {0!r}>".format(self.number)

    def __repr__(self):
        return "AnonymousStorageId()"

    def __hash__(self):
        return hash(self.number)

    def __eq__(self, other):
        return (
            isinstance(other, AnonymousStorageId) and
            self.number == other.number
        )

    @classmethod
    def from_path_stat(cls, path, stat):
        return cls()


class UnixStorageId(object):
    def __init__(self, device_num, inode_num):
        self.device_num = device_num
        self.inode_num = inode_num

    def presentation_string(self):
        return str(self)

    def __str__(self):
        return "dev {0:#018x}, ino {1:#018x}".format(self.device_num, self.inode_num)

    def __repr__(self):
        return "UnixStorageId({0!r}, {1!r})".format(self.device_num, self.inode_num)

    def __hash__(self):
        return hash(self.device_num) ^ hash(self.inode_num)

    def __eq__(self, other):
        return (
            isinstance(other, UnixStorageId) and
            self.device_num == other.device_num and
            self.inode_num == other.inode_num
        )

    @classmethod
    def from_path_stat(cls, path, stat):
        return cls(stat.st_dev, stat.st_ino)
