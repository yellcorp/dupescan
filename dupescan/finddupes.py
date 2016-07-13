import dupescan

import argparse
import itertools
import os
import sys


__all__ = [ "execute_report", "scan", "run" ] 


def get_arg_parser():
    p = argparse.ArgumentParser(
        description="Find files with identical content."
    )

    p.add_argument("paths",
        nargs="*",
        metavar="PATH",
        help="""List of files to consider. Specify --recurse (-r) to also
                consider the contents of directories."""
    )

    p.add_argument("-s", "--symlinks",
        action="store_true",
        help="""Include symlinks."""
    )

    p.add_argument("-z", "--zero",
        action="store_true",
        help="""Include zero-length files. All zero-length files are considered
                to have identical content."""
    )

    p.add_argument("-a", "--aliases",
        action="store_true",
        help="""Check whether a single file has more than one name, which is
                possible through hardlinks, as well as symlinks if the
                -s/--symlinks option is specified. This check is used to skip
                redundant content comparisons, add extra information to
                reports, and preserve all paths pointing to a selected file
                when the -p/--prefer option is used."""
    )

    p.add_argument("-r", "--recurse",
        action="store_true",
        help="""Recurse into subdirectories."""
    )

    p.add_argument("-p", "--prefer",
        metavar="CRITERIA",
        help="""For each set of duplicate files, automatically select one
                for preservation according to the provided criteria. Other
                duplicates can be deleted by passing the generated report to
                the -x/--execute option."""
    )

    p.add_argument("--help-prefer",
        action="store_true",
        help="""Display detailed help on using the --prefer option"""
    )

    p.add_argument("-v", "--verbose",
        action="store_true",
        help="""Log detailed information to STDERR."""
    )

    p.add_argument("-x", "--execute",
        metavar="PATH",
        help="""Delete unmarked files in the report at %(metavar)s. Sets where
                no files are marked will be skipped."""
    )

    p.add_argument("-n", "--dry-run",
        action="store_true",
        help="""Used in combination with -x/--execute. List actions that
                --execute would perform without actually doing them."""
    )

    return p


PREFER_HELP="""
When {script_name} is run with the --prefer option, it will examine each set of
duplicate files discovered, and attempt to mark one of them as 'preferred',
according to a set of criteria provided by the user.

Example:

    $ {script_name} -r . --prefer "shorter path"
    ## Size: 100K Instances: 3 Excess: 200K Names: 3
      ./Copy of photo.jpg
      ./backup/photo.jpg
    > ./photo.jpg

In this case 'photo.jpg' is the preferred copy because it has the shortest
path.

This report can then be used to delete the non-preferred duplicates by saving
the report to a file and rerunning {script_name} with the --execute option.

A criteria string is a phrase, or a series of phrases, expressing what
properties of a file should make it the preferred one among a set of
duplicates.  For each set of duplicates, the selection process begins with all
files marked.  Each phrase, starting with the first, is tested against the
marked files, and those that do not pass are unmarked.  Phrases are considered
until only one file is marked, or there are no more phrases.

If the selection process ends with a single file, it is indicated in the report
with a '>' symbol. If there remains more than one file marked, they are
indicated with '?'.

Example:

    $ {script_name} -r . --prefer "shorter path"
    ## Size: 100K Instances: 4 Excess: 300K Names: 4
      ./Copy of photo2.jpg
      ./backup/photo1.jpg
    ? ./photo1.jpg
    ? ./photo2.jpg

In this case, both 'photo1.jpg' and 'photo2.jpg' are marked because there is no
single shortest path, and there are no other criteria to prefer one of these
over the other. This could be resolved with a second criteria, for example:

    $ {script_name} -r . --prefer "shorter path, earlier path"
    ## Size: 100K Instances: 4 Excess: 300K Names: 4
      ./Copy of photo2.jpg
      ./backup/photo1.jpg
    > ./photo1.jpg
      ./photo2.jpg

In this sense, 'earlier' means lexicographically earlier, or lesser - a name
that appears earlier in a list when sorted.  Now 'photo1.jpg' wins over
'photo2.jpg'.  Note that 'Copy of photo2.jpg' is not considered, even though it
sorts earliest of all, because it was eliminated by the first 'shorter path'
criterion.

Criteria strings make use of spaces, so the entire set of criteria phrases must
be escaped appropriately for your shell. Generally this means surrounding them
with single or double quotes.

A criteria string must be a single argument that follows the --prefer option,
and has the following grammar.

CRITERIA : PHRASE ( , PHRASE ) +
  A CRITERIA is a one or more PHRASEs, separated by commas (,).

PHRASE : BOOLEAN_PHRASE | EXTREMA_PHRASE
  A PHRASE is a BOOLEAN_PHRASE or a EXTREMA_PHRASE.

BOOLEAN_PHRASE : PROPERTY OPERATOR ARGUMENT [ MODIFIER ]
  Such phrases prefer files that pass some kind of a true/false test.

EXTREMA_PHRASE : ADJECTIVE PROPERTY [ MODIFIER ]
  Such phrases prefer files that occur first or last when sorted by some
  property.

PROPERTY  : path
            The file's full path, relative to the working directory.

          | name
            The file's name - that is, the path from just after the last
            directory separator to the end.

          | directory
            The file's containing directory - that is, the path up until the
            last directory separator.

          | directory name
            The name of the file's containing directory - that is, the path
            between the second-last path separator and the last one.

          | extension
            The file's extension, including the '.' if present.  If the file
            lacks an extension, it is considered to be "" - the empty string.

          | mtime
          | modification time
            The file's modification time.

OPERATOR  : is
            Prefer strings that are equal to the argument.

          | is not
            Prefer strings that are not equal to the argument.

          | contains
            Prefer strings that contain the argument.

          | not contains
            Prefer strings that do not contain the argument.

          | starts with
            Prefer strings in which the argument occurs at the start.

          | not starts with
            Prefer strings in which the argument does not occur at the start.

          | ends with
            Prefer strings in which the argument occurs at the end.

          | not ends with
            Prefer strings in which the argument does not occur at the end.

          | matches re
          | matches regex
          | matches regexp
            Interpret the argument as a regular expression, and prefer strings
            that match it.

          | not matches re
          | not matches regex
          | not matches regexp
            Prefer strings that do not match the argument.

ADJECTIVE : shorter
            Prefer shorter strings.

          | longer
            Prefer longer strings.

          | shallower
            Prefer strings containing fewer directory separators.

          | deeper
            Prefer strings containing more directory separators.

          | earlier
            When used with strings: prefer ones that appear earlier when sorted.
            When used with times: prefer earlier ones.

          | later
            When used with strings: prefer ones that appear later when sorted.
            When used with times: prefer later ones.

ARGUMENT  : BARE_STRING
            A sequence of characters terminated by the first unescaped space.
            Spaces and backslashes can be included by prepending them with a
            backslash (\\).

          | SINGLE_QUOTED_STRING
            A sequence of characters surrounded by single quotes ('). Single
            quotes and backslashes can be included by prepending them with a
            backslash (\\).

          | DOUBLE_QUOTED_STRING
            A sequence of characters surrounded by double quotes ("). Double
            quotes and backslashes can be included by prepending them with a
            backslash (\\).

MODIFIER  : ignoring case
  This will cause all string comparisons and tests to ignore letter case.
"""


SELECTION_MARKER_UNIQUE =    ">"
SELECTION_MARKER_NONUNIQUE = "?"
class Reporter(object):
    def __init__(self, show_hardlink_info=True, selector_func=None, output_stream=sys.stdout):
        self.show_hardlink_info = show_hardlink_info
        self.selector_func = selector_func
        self.output_stream = output_stream

    def _print(self, *args):
        print(*args, file=self.output_stream)

    def handle_dupe_set(self, dupe_set):
        file_size = os.stat(dupe_set[0].path()).st_size

        self._print("## Size: {file_size} Instances: {inst_count} Excess: {excess_size} Names: {name_count}".format(
            inst_count=len(dupe_set),
            name_count=sum(len(instance.paths) for instance in dupe_set),
            file_size=dupescan.unitformat.format_file_size(file_size),
            excess_size=dupescan.unitformat.format_file_size(file_size * (len(dupe_set) - 1))
        ))

        selected_paths = set()
        selected_instances = set()
        if self.selector_func is not None:
            all_names = itertools.chain(*(instance.paths for instance in dupe_set))
            try:
                selected_paths.update(self.selector_func.pick(all_names))
                for instance in dupe_set:
                    if len(selected_paths.intersection(instance.paths)) > 0:
                        selected_instances.add(instance)
            except EnvironmentError as ee:
                self._print("## Skipping selection due to error: {!s}".format(ee))

        keep_marker = (
            SELECTION_MARKER_UNIQUE if len(selected_instances) == 1
            else SELECTION_MARKER_NONUNIQUE
        )

        instance_header = self.show_hardlink_info
        for index, instance in enumerate(
            sorted(
                dupe_set,
                key=lambda i: len(i.paths), reverse=True
            )
        ):
            if instance_header:
                if len(instance.paths) == 1:
                    self._print("# Separate instances follow")
                    instance_header = False
                else:
                    self._print("# Instance {}".format(index + 1))

            for path in sorted(instance.paths):
                self._print("{keep_marker} {path}".format(
                    keep_marker=keep_marker if instance in selected_instances else " ",
                    path=dupescan.report.format_path(path)
                ))
        self._print()


def and_funcs(f, g):
    if f is None:
        return g
    if g is None:
        return f

    def h(a):
        return f(a) and g(a)
    return h


def create_walker(paths, recurse=False, include_empty_files=False, include_symlinks=False):
    zero_filter = None
    if not include_empty_files:
        zero_filter = lambda f: os.stat(f).st_size > 0

    symlink_filter = None
    if not include_symlinks:
        symlink_filter = lambda f: not os.path.islink(f)

    file_filter = and_funcs(symlink_filter, zero_filter)
    dir_filter = symlink_filter

    if recurse:
        return dupescan.walk.recurse_iterator(paths, dir_filter, file_filter)
    else:
        return [
            p for p in paths
            if (
                dir_filter(p) if os.path.isdir(p) else file_filter(p)
            )
        ]


def create_reporter(prefer=None, report_hardlinks=False):
    selector = None
    if prefer:
        selector = dupescan.criteria.parse_selector(prefer)

    return Reporter(show_hardlink_info=report_hardlinks, selector_func=selector)


def execute_report(report_path, dry_run):
    errors = False
    with open(report_path, "r") as report_stream:
        for marked, unmarked in dupescan.report.parse_report(report_stream):
            if len(marked) > 0:
                for path in unmarked:
                    print(path, end="")
                    if not dry_run:
                        try:
                            os.remove(path)
                        except EnvironmentError as ee:
                            print(": {!s}".format(ee), end="")
                            errors = True
                    print()
    return 2 if errors else 0


def scan(
    paths,
    recurse=False,
    include_empty_files=False,
    include_symlinks=False,
    report_hardlinks=False,
    prefer=None,
    verbose=False
):
    walker = create_walker(paths, recurse, include_empty_files, include_symlinks)
    reporter = create_reporter(prefer, report_hardlinks)

    for dupe_set in dupescan.find_duplicate_files(
        walker,
        collect_inodes=report_hardlinks,
        unique_paths=True,
        error_cb="print_stderr",
        log_cb="print_stderr" if verbose else None
    ):
        reporter.handle_dupe_set(dupe_set)


def run(argv=None):
    p = get_arg_parser()
    args = p.parse_args(argv)

    if args.help_prefer:
        print(PREFER_HELP.strip().format(script_name=os.path.basename(sys.argv[0])))
        return 0

    if args.execute is None:
        if args.dry_run:
            print("Warning: -n/--dry-run has no effect if -x/--execute is not specified.", file=sys.stderr)
        scan(
            paths=args.paths,
            recurse=args.recurse,
            include_empty_files=args.zero,
            include_symlinks=args.symlinks,
            report_hardlinks=args.aliases,
            prefer=args.prefer,
            verbose=args.verbose
        )
        return 0

    else:
        if any((
            args.paths,
            args.symlinks,
            args.zero,
            args.aliases,
            args.recurse,
            args.prefer
        )):
            print("Only -n/--dry-run can be used with -x/--execute. All other options must be omitted.", file=sys.stderr)
            return 1

        return execute_report(args.execute, args.dry_run)


def main():
    # TODO: take another look at the exact script generated by setup.py and
    # tweak this
    sys.exit(run(sys.argv[1:]))
