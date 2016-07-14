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
        help="""List files that appear in both directories."""
    )

    p.add_argument("-r", "--removes",
        action="store_true",
        help="""List files that appear only as a descendant of the first directory."""
    )

    p.add_argument("-a", "--adds",
        action="store_true",
        help="""List files that appear only as a descendant of the second directory."""
    )

    p.add_argument("-c", "--colorize",
        dest="colorize",
        default=None,
        action="store_true",
        help="""Colorize output."""
    )

    p.add_argument("--no-colorize",
        dest="colorize",
        action="store_false",
        help="""Force colorizing off. If neither --colorize or --no-colorize is
                specified, it will be enabled if a compatible terminal is
                detected."""
    )

    p.add_argument("--no-summary",
        action="store_true",
        help="""Suppress the summary."""
    )

    p.add_argument("--version",
        action="version",
        version="%(prog)s " + dupescan.__version__
    )

    return p


MATCH = 1
ADDED = 2
REMOVED = 4
ACTION_ORDER = (MATCH, ADDED, REMOVED)
ALL_ACTIONS = sum(ACTION_ORDER)
def correlate(root1, root2, verbose=False):
    origin = collections.defaultdict(int)

    def iter_origin():
        for path, bits in origin.items():
            if bits & 1:
                yield path
            if bits & 2:
                yield path

    ignore_symlinks = lambda f: not os.path.islink(f)
    for root, bit in ((root1, 1), (root2, 2)):
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


ACTION_STRINGS = {
    MATCH:   ("=", "Matches", None),
    ADDED:   ("+", "Adds",    "32"),
    REMOVED: ("-", "Removes", "31")
}
SYMBOL = 0
SUMMARY_WORD = 1
DEFAULT_SGR = 2


def format_ansi_sgr(string, sgr):
    if sgr is None:
        return string
    return "\x1b[{}m{}\x1b[0m".format(sgr, string)


def print_report(
    root1, root2,
    filter_actions=ALL_ACTIONS,
    ansi=None, # None: autodetect, True: use default, False: no colors, or tuple of 3 things to appear between \x1b[ and m
    summary=True,
    verbose=False,
    file=None
):
    if file is None:
        file = sys.stdout

    if ansi is None:
        try:
            ansi = file.isatty()
        except AttributeError:
            ansi = False

    if ansi is True:
        ansi = tuple(
            ACTION_STRINGS[action][DEFAULT_SGR]
            for action in ACTION_ORDER
        )
    elif ansi is False:
        ansi = (None, None, None)

    sgr_lookup = dict(zip(ACTION_ORDER, ansi))

    action_count = collections.Counter()

    for action, path1, path2 in correlate(root1, root2, verbose=verbose):
        action_count[action] += 1
        if filter_actions & action:
            symbol = ACTION_STRINGS[action][SYMBOL]

            if path1 is not None:
                print(format_ansi_sgr(
                    "{} {}".format(symbol, dupescan.report.format_path(path1)),
                    sgr_lookup[action]
                ), file=file)
                symbol = " "

            if path2 is not None:
                print(format_ansi_sgr(
                    "{} {}".format(symbol, dupescan.report.format_path(path2)),
                    sgr_lookup[action]
                ), file=file)

            print()

    if summary:
        print(
            "# " +
            ", ".join(
                "{}: {}".format(ACTION_STRINGS[action][SUMMARY_WORD], action_count[action])
                for action in (MATCH, ADDED, REMOVED)
            ),
            file=file
        )


def run(argv=None):
    p = get_arg_parser()
    args = p.parse_args(argv)

    filter_actions = sum(
        action for
        action, select in (
            (MATCH,   args.matches),
            (ADDED,   args.adds),
            (REMOVED, args.removes)
        )
        if select
    )

    if filter_actions == 0:
        filter_actions = ALL_ACTIONS

    print_report(
        *args.dirs,
        filter_actions=filter_actions,
        ansi=args.colorize,
        summary=not args.no_summary,
        verbose=args.verbose,
        file=sys.stdout
    )

    return 0


def main():
    return run(sys.argv[1:])
