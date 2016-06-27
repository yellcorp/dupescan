#!/usr/bin/env python3

import dupelib

import argparse
import os
import sys


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


def run_report(report_path, dry_run):
    errors = False
    with open(report_path, "r") as report_stream:
        for marked, unmarked in dupelib.report.parse_report(report_stream):
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


def main():
    p = get_arg_parser()
    args = p.parse_args()

    if args.execute is None:
        if args.dry_run:
            print("Warning: -n/--dry-run has no effect if -x/--execute is not specified.", file=sys.stderr)
        dupelib.programs.finddupes_report(
            paths=args.paths,
            recurse=args.recurse,
            include_empty_files=args.zero,
            include_symlinks=args.symlinks,
            report_hardlinks=args.aliases,
            prefer=args.prefer
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

        return run_report(args.execute, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
