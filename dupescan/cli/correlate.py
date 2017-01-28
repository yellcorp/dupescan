import argparse
import collections
from enum import Enum
import functools
import itertools
import sys

from dupescan import (
    core,
    fs,
    log,
)
from dupescan.cli._common import add_common_cli_args


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

    add_common_cli_args(p)

    return p


class Action(Enum):
    match = 1
    added = 2
    removed = 4


ACTION_STRINGS = {
    Action.match:   ("matches", "=", "Matches", None),
    Action.added:   ("adds",    "+", "Adds",    "32"),
    Action.removed: ("removes", "-", "Removes", "31")
}
ARG_NAME = 0
SYMBOL = 1
SUMMARY_WORD = 2
DEFAULT_SGR = 3


def main():
    return run(sys.argv[1:])


def run(argv=None):
    p = get_arg_parser()
    args = p.parse_args(argv)

    config = CorrelateConfig()
    config.include_actions = set(
        action
        for action, strings in ACTION_STRINGS.items()
        if getattr(args, strings[ARG_NAME])
    )
    if len(config.include_actions) == 0:
        config.include_actions = set(Action)

    config.ansi = args.colorize
    config.summary = not args.no_summary
    config.verbose = args.verbose
    config.file = sys.stdout
    config.buffer_size = args.buffer_size,

    generate_report(*args.dirs, config)

    return 0


class CorrelateConfig(object):
    def __init__(self):
        self.include_actions = None

        # None: autodetect, True: use default, False: no colors, or tuple of 3 things to appear between \x1b[ and m
        self.ansi = None

        self.summary = True
        self.verbose = False
        self.file = sys.stdout
        self.buffer_size = None


def generate_report(root1, root2, config):
    if config.include_actions is None or len(config.include_actions) == 0:
        include_actions = set(Action)
    else:
        include_actions = set(config.include_actions)

    file = config.file if config.file is not None else sys.stdout
    out = functools.partial(print, file=file)

    sgr_lookup = interpret_ansi_param(config.ansi, file)

    action_count = collections.Counter()

    logger = log.StreamLogger(
        stream = sys.stderr,
        min_level=log.DEBUG if config.verbose else log.INFO,
    )

    dupe_finder = core.DuplicateFinder(
        buffer_size = config.buffer_size,
        logger = logger,
    )

    for action, entry1, entry2 in correlate(dupe_finder, root1, root2):
        action_count[action] += 1

        if action not in include_actions:
            continue

        symbol = ACTION_STRINGS[action][SYMBOL]
        for entry in (entry1, entry2):
            if entry is None:
                continue
            out(format_ansi_sgr(
                "%s %r" % (symbol, entry.path),
                sgr_lookup[action]
            ))
            symbol = " "

        out("")

    if config.summary:
        counts = (
            "%s: %s" % (ACTION_STRINGS[action][SUMMARY_WORD], action_count[action])
            for action in Action
        )
        out("# " + ", ".join(counts))


def correlate(dupe_finder, root1, root2):
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

    for dupe_set in dupe_finder(entry_iter):
        partitions = ([ ], [ ])
        for instance in dupe_set:
            partitions[instance.entry.root_index].append(instance.entry)
            all_entries.remove(instance.entry)

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


def tap_iterator(member_function, input_iterator):
    for member in input_iterator:
        member_function(member)
        yield member


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
