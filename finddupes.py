#!/usr/bin/env python3

import dupelib

import argparse
import itertools
import os


def get_arg_parser():
    p = argparse.ArgumentParser(
        description="Find files with identical content"
    )

    p.add_argument("paths",
        nargs="*",
        metavar="PATH",
        help="""List of files to consider. Specify --recurse (-r) to also
                consider the contents of directories"""
    )

    p.add_argument("-s", "--symlinks",
        action="store_true",
        help="""Include symlinks"""
    )

    p.add_argument("-z", "--zero",
        action="store_true",
        help="""Include zero-length files"""
    )

    p.add_argument("-a", "--aliases",
        action="store_true",
        help="""Check whether a single file has more than one name, which is
                possible through hardlinks, as well as symlinks if the
                --symlinks option is specified. This check is used to skip
                redundant content comparisons, add extra information to
                reports, and preserve all paths pointing to a selected file
                when the --prefer option is used."""
    )

    p.add_argument("-r", "--recurse",
        action="store_true",
        help="""Recurse into subdirectories"""
    )

    p.add_argument("-p", "--prefer",
        metavar="CRITERIA",
        help="""For each set of duplicate files, automatically select one
                according to the provided criteria."""
    )

    p.add_argument("-x", "--execute",
        metavar="PATH",
        help="""Delete unmarked files in the report at %(metavar)s. Sets where
                no files are marked will be skipped."""
    )

    return p


SELECTION_MARKER_UNIQUE =    ">"
SELECTION_MARKER_NONUNIQUE = "*"
def handle_dupe_set(dupe_set, hardlink_info=True, selector=None):
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
        all_names = itertools.chain(instance.paths for instance in dupe_set) 
        try:
            selected_paths.update(selector.pick(all_names))
            for instance in selected_instances:
                if len(selected_paths.intersection(instance.paths)) > 0:
                    selected_instances.add(instance)
        except EnvironmentError as ee:
            print("## Skipping selection due to error: {!s}".format(ee))

    if len(selected_instances) == 1:
        keep_marker = SELECTION_MARKER_UNIQUE
    else:
        keep_marker = SELECTION_MARKER_NONUNIQUE

    instance_header = hardlink_info
    for index, instance in enumerate(sorted(dupe_set, key=lambda i: len(i.paths), reverse=True)):
        if instance_header:
            if len(instance.paths) == 1:
                print("# Separate instances follow")
                instance_header = False
            else:
                print("# Instance {}".format(index + 1))
        for path in sorted(instance.paths):
            print("{keep_marker} {path}".format(
                keep_marker=keep_marker if instance in selected_instances else " ",
                path=path
            ))
    print()


def main():
    p = get_arg_parser()
    args = p.parse_args()

    selector = None
    if args.prefer:
        selector = dupelib.criteria.parse_selector(args.prefer)

    if args.execute:
        raise NotImplementedError("--execute")

    if args.zero:
        raise NotImplementedError("--zero")

    if args.symlinks:
        raise NotImplementedError("--symlinks")

    if args.recurse:
        path_iterator = dupelib.walk.recurse_iterator(args.paths)
    else:
        path_iterator = args.paths

    for dupe_set in dupelib.find_duplicate_files(
        path_iterator,
        collect_inodes=args.aliases,
        error_cb="print_stderr",
        #log_cb="print_stderr"
    ):
        handle_dupe_set(dupe_set, hardlink_info=args.aliases, selector=selector)


if __name__ == "__main__":
    main()
