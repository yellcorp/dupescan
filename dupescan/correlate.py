import argparse
import collections
from enum import Enum
import functools
import itertools
import sys

from dupescan import (
    __version__,
    algo,
    fs,
    report,
)


__all__ = ("correlate", "generate_report", "run")


def get_arg_parser():
    p = argparse.ArgumentParser(
        description="Compare two directories by content.",
        epilog="""If none of -m/--matches, -r/--removes, -a/--adds is
                  specified, all are reported."""
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
        version="%(prog)s " + __version__
    )

    return p


class Action(Enum):
    match = 1
    added = 2
    removed = 4


def tap_iterator(member_function, input_iterator):
    for member in input_iterator:
        member_function(member)
        yield member


def correlate(root1, root2, verbose=False):
    all_entries = set()
    ignore_symlinks = lambda e: not e.is_symlink

    entry_iter = tap_iterator(
        all_entries.add,
        fs.recurse_iterator(
            (root1, root2),
            ignore_symlinks,
            ignore_symlinks
        )
    )

    find_dupes = algo.DuplicateFinder(
        # buffer_size = buffer_size,
    )

    for dupe_set in find_dupes(entry_iter):
        partitions = ([ ], [ ])
        for content in dupe_set:
            partitions[content.entry.root_index].append(content.entry)
            all_entries.remove(content.entry)

        for a, b in itertools.zip_longest(*partitions):
            assert not (a is None and b is None), "got (None, None) from zip_longest"

            if a is None:
                action = Action.added
            elif b is None:
                action = Action.removed
            else:
                action = Action.match

            yield action, a, b

    for entry in all_entries:
        assert entry.root_index in (0, 1), "bad root_index while iterating unmatched entries"
        if entry.root_index == 0:
            yield Action.removed, entry, None
        else:
            yield Action.added, None, entry


ACTION_STRINGS = {
    Action.match:   ("matches", "=", "Matches", None),
    Action.added:   ("adds",    "+", "Adds",    "32"),
    Action.removed: ("removes", "-", "Removes", "31")
}
ARG_NAME = 0
SYMBOL = 1
SUMMARY_WORD = 2
DEFAULT_SGR = 3


def format_ansi_sgr(string, sgr):
    if sgr is None:
        return string
    return "\x1b[%sm%s\x1b[0m" % (sgr, string)


def interpret_ansi_param(ansi, out_stream):
    if ansi is None:
        try:
            ansi = out_stream.isatty()
        except AttributeError:
            ansi = False

    if ansi is True:
        return {
            action: strings[DEFAULT_SGR]
            for action, strings in ACTION_STRINGS.items()
        }

    if ansi is False:
        return {
            action: None
            for action in Action
        }

    return dict(zip(Action, ansi))


def generate_report(
    root1, root2,
    include_actions=None,
    ansi=None, # None: autodetect, True: use default, False: no colors, or tuple of 3 things to appear between \x1b[ and m
    summary=True,
    verbose=False,
    file=None
):
    if include_actions is None or len(include_actions) == 0:
        include_actions = set(Action)
    else:
        include_actions = set(include_actions)

    if file is None:
        file = sys.stdout
    out = functools.partial(print, file=file)

    sgr_lookup = interpret_ansi_param(ansi, file)

    action_count = collections.Counter()
    for action, entry1, entry2 in correlate(root1, root2, verbose=verbose):
        action_count[action] += 1

        if action not in include_actions:
            continue

        symbol = ACTION_STRINGS[action][SYMBOL]
        for entry in (entry1, entry2):
            if entry is None:
                continue
            out(format_ansi_sgr(
                "%s %s" % (symbol, report.format_path(entry.path)),
                sgr_lookup[action]
            ))
            symbol = " "

        out("")

    if summary:
        counts = (
            "%s: %s" % (ACTION_STRINGS[action][SUMMARY_WORD], action_count[action])
            for action in Action
        )
        out("# " + ", ".join(counts))


def run(argv=None):
    p = get_arg_parser()
    args = p.parse_args(argv)

    include_actions = set(
        action
        for action, strings in ACTION_STRINGS.items()
        if getattr(args, strings[ARG_NAME])
    )

    if len(include_actions) == 0:
        include_actions = set(Action)

    generate_report(
        *args.dirs,
        include_actions=include_actions,
        ansi=args.colorize,
        summary=not args.no_summary,
        verbose=args.verbose,
        file=sys.stdout
    )

    return 0


def main():
    return run(sys.argv[1:])
