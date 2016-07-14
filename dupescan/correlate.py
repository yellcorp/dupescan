import dupescan

import argparse
import collections
import itertools
import os
import sys


__all__ = [ "correlate", "run" ] 


def get_arg_parser():
    p = argparse.ArgumentParser(
        description="Compare two directories by content."
    )

    p.add_argument("dirs",
        nargs=2,
        metavar="DIR",
        help="""Paths to the directories to be compared."""
    )

    #p.add_argument("-s", "--symlinks",
        #action="store_true",
        #help="""Include symlinks."""
    #)

    p.add_argument("-v", "--verbose",
        action="store_true",
        help="""Log detailed information to STDERR."""
    )

    p.add_argument("-m", "--matches",
        action="store_true",
        help="""List files that appear in both directories"""
    )

    p.add_argument("-r", "--removes",
        action="store_true",
        help="""List files that appear only as a descendant of the first directory"""
    )

    p.add_argument("-a", "--adds",
        action="store_true",
        help="""List files that appear only as a descendant of the second directory"""
    )

    p.add_argument("--version",
        action="version",
        version="%(prog)s " + dupescan.__version__
    )

    return p


MATCH = 1
ADDED = 2
REMOVED = 3
def correlate(
    path1, path2,
    verbose=False
):
    origin = collections.defaultdict(int)

    def iter_origin():
        for path, bits in origin.items():
            if bits & 1:
                yield path
            if bits & 2:
                yield path

    ignore_symlinks = lambda f: not os.path.islink(f)
    for root, bit in ((path1, 1), (path2, 2)):
        for path in dupescan.walk.recurse_iterator((root,), ignore_symlinks, ignore_symlinks):
            origin[path] |= bit 

    for dupe_set in dupescan.find_duplicate_files(
        iter_origin(),
        collect_inodes=False,
        unique_paths=False,
        error_cb="print_stderr",
        log_cb="print_stderr" if verbose else None
    ):
        partitions = [ [ ], [ ] ]
        for instance in dupe_set:
            path = instance.path()

            if origin[path] & 1:
                partitions[0].append(path)
                origin[path] &= ~1

            elif origin[path] & 2:
                partitions[1].append(path)
                origin[path] &= ~2

            if origin[path] == 0:
                del origin[path]

        for a, b in itertools.zip_longest(*partitions):
            if a is None:
                # in this case, b cannot be None. b was added
                assert b is not None, "zip_longest somehow yielded (None, None)"
                action = ADDED
            else: # a is not None
                if b is None:
                    # a was removed
                    action = REMOVED
                else:
                    # a and b match
                    action = MATCH

            yield (action, a, b)

    # origin paths are removed as they are encountered. all that remains at
    # this point will be files that weren't matched in the other root
    for path, bit in origin.items():
        assert bit not in (0, 3), "{!r} has invalid value {}".format(path, bit)
        if bit == 1:
            yield (REMOVED, path, None)
        else:
            yield (ADDED, None, path)


SYMBOLS = {
    MATCH:   "=",
    ADDED:   "+",
    REMOVED: "-"
}
def run(argv=None):
    p = get_arg_parser()
    args = p.parse_args(argv)

    subscribed_actions = set(
        action for
        action, select in (
            (MATCH,   args.matches),
            (ADDED,   args.adds),
            (REMOVED, args.removes)
        )
        if select
    )

    if len(subscribed_actions) == 0:
        subscribed_actions = { MATCH, ADDED, REMOVED }

    for action, path1, path2 in correlate(*args.dirs, verbose=args.verbose):
        # TODO: formatters
        if action in subscribed_actions:
            print("{} {}\t{}".format(SYMBOLS[action], path1 or "", path2 or ""))

    return 0


def main():
    return run(sys.argv[1:])
