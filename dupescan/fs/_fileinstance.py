import itertools


class FileInstance(object):
    """A single file (inode) with one or more FileSystemEntries pointing to it"""

    __slots__ = ("address", "entries")

    def __init__(self, address, entries=None, entry=None):
        self.address = address

        # optimization - reduce copying if possible
        if entry is None and isinstance(entries, tuple):
            self.entries = entries
        elif entries is None:
            self.entries = (entry,)
        else:
            # under any other condition, do a full massage of the ctor parameters
            self.entries = tuple(itertools.chain(
                entries if entries is not None else (),
                (entry,) if entry is not None else ()
            ))

    def __hash__(self):
        return hash(self.address) ^ hash(self.entries)

    def __eq__(self, other):
        return (
            isinstance(other, FileInstance) and
            self.address == other.address and
            self.entries == other.entries
        )

    def __str__(self):
        return self.entries[0].path if len(self.entries) > 0 else ""

    def __repr__(self):
        return "%s(%r, entries=%r)" % (
            type(self).__name__,
            self.address,
            self.entries,
        )

    @property
    def entry(self):
        return self.entries[0] if len(self.entries) > 0 else None
