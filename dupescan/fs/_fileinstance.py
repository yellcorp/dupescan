import collections
import itertools
from typing import Iterator, Iterable, Dict, Hashable, List, Optional

from dupescan.fs import FileEntry


class FileInstance(object):
    """A single file (inode) with one or more FileSystemEntries pointing to it"""

    __slots__ = ("identifier", "entries")

    def __init__(self, identifier, entries=None, entry=None):
        self.identifier = identifier

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
        return hash(self.identifier) ^ hash(self.entries)

    def __eq__(self, other):
        return (
            isinstance(other, FileInstance) and
            self.identifier == other.identifier and
            self.entries == other.entries
        )

    def __str__(self):
        return self.entries[0].path if len(self.entries) > 0 else ""

    def __repr__(self):
        return "%s(%r, entries=%r)" % (
            type(self).__name__,
            self.identifier,
            self.entries,
        )

    @property
    def entry(self) -> Optional[FileEntry]:
        return self.entries[0] if len(self.entries) > 0 else None

    @classmethod
    def group_entries_by_identifier(cls, entries: Iterable[FileEntry]) -> Iterator['FileInstance']:
        groups: Dict[Hashable, List[FileEntry]] = collections.defaultdict(list)
        for entry in entries:
            groups[entry.uid].append(entry)

        for uid, entries in groups.items():
            yield cls(identifier=uid, entries=entries)
