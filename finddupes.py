#!/usr/bin/env python3

import dupelib

import argparse
import itertools
import os


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

    return p


SELECTION_MARKER_UNIQUE =    ">"
SELECTION_MARKER_NONUNIQUE = "?"
def handle_dupe_set(dupe_set, show_hardlink_info=True, selector=None):
    file_size = os.stat(dupe_set[0].path()).st_size

    print("## Size: {file_size} Instances: {inst_count} Excess: {excess_size} Names: {name_count}".format(
        inst_count=len(dupe_set),
        name_count=sum(len(instance.paths) for instance in dupe_set),
        file_size=dupelib.unitformat.format_file_size(file_size),
        excess_size=dupelib.unitformat.format_file_size(file_size * (len(dupe_set) - 1))
    ))

    selected_paths = set()
    selected_instances = set()
    if selector is not None:
        all_names = itertools.chain(*(instance.paths for instance in dupe_set))
        try:
            selected_paths.update(selector.pick(all_names))
            for instance in dupe_set:
                if len(selected_paths.intersection(instance.paths)) > 0:
                    selected_instances.add(instance)
        except EnvironmentError as ee:
            print("## Skipping selection due to error: {!s}".format(ee))

    keep_marker = (
        SELECTION_MARKER_UNIQUE if len(selected_instances) == 1
        else SELECTION_MARKER_NONUNIQUE
    )

    instance_header = show_hardlink_info
    for index, instance in enumerate(
        sorted(
            dupe_set,
            key=lambda i: len(i.paths), reverse=True
        )
    ):
        if instance_header:
            if len(instance.paths) == 1:
                print("# Separate instances follow")
                instance_header = False
            else:
                print("# Instance {}".format(index + 1))

        for path in sorted(instance.paths):
            print("{keep_marker} {path}".format(
                keep_marker=keep_marker if instance in selected_instances else " ",
                path=dupelib.report.format_path(path)
            ))
    print()


def and_funcs(f, g):
    if f is None:
        return g
    if g is None:
        return f

    def h(a):
        return f(a) and g(a)
    return h


def main():
    p = get_arg_parser()
    args = p.parse_args()

    selector = None
    if args.prefer:
        selector = dupelib.criteria.parse_selector(args.prefer)

    if args.execute:
        raise NotImplementedError("--execute")

    link_filter = None
    if not args.symlinks:
        link_filter = lambda f: not os.path.islink(f)

    zero_filter = None
    if not args.zero:
        zero_filter = lambda f: os.stat(f).st_size > 0

    file_filter = and_funcs(link_filter, zero_filter)
    dir_filter = link_filter

    if args.recurse:
        path_iterator = dupelib.walk.recurse_iterator(args.paths, dir_filter, file_filter)
    else:
        path_iterator = [
            p for p in args.paths
            if (
                dir_filter(p) if os.path.isdir(p) else file_filter(p)
            )
        ]

    for dupe_set in dupelib.find_duplicate_files(
        path_iterator,
        collect_inodes=args.aliases,
        error_cb="print_stderr",
        #log_cb="print_stderr"
    ):
        handle_dupe_set(dupe_set, show_hardlink_info=args.aliases, selector=selector)


if __name__ == "__main__":
    main()
