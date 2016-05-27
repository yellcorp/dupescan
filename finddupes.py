#!/usr/bin/env python3

import dupelib

import argparse
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

    p.add_argument("-l", "--symlinks",
        action="store_true",
        help="""Include symlinks"""
    )

    p.add_argument("-z", "--zero",
        action="store_true",
        help="""Include zero-length files"""
    )

    p.add_argument("-h", "--hardlinks",
        action="store_true",
        help="""Check for hardlinks. If this option is specified, hardlinks
                will be preserved in autoselect criteria, be used to skip
                redundant content comparisons, and information about them will
                appear in reports."""
    )

    p.add_argument("-r", "--recurse",
        action="store_true",
        help="""Recurse into subdirectories"""
    )

    p.add_argument("-a", "--autoselect",
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


def handle_dupe_set(dupe_set, hardlink_info=True):
    # TODO: autoselecting, like --prefer in the old one
    file_size = os.stat(dupe_set[0].path()).st_size
    selected = None

    print("## Size: {file_size} Instances: {inst_count} Excess: {excess_size} Names: {name_count}".format(
        inst_count=len(dupe_set),
        name_count=sum(len(instance.paths) for instance in dupe_set),
        file_size=dupelib.format_file_size(file_size),
        excess_size=dupelib.format_file_size(file_size * (len(dupe_set) - 1))
    ))

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
                keep_marker=">" if selected == instance else " ",
                path=path
            ))
    print()


def main():
    p = get_arg_parser()
    args = p.parse_args()

    if args.autoselect:
        raise NotImplementedError("--autoselect")

    if args.execute:
        raise NotImplementedError("--execute")

    if args.zero:
        raise NotImplementedError("--zero")

    if args.symlinks:
        raise NotImplementedError("--hardlinks")

    if args.recurse:
        path_iterator = dupelib.recurse_iterator(args.paths)
    else:
        path_iterator = args.paths

    for dupe_set in dupelib.find_duplicate_files(
        path_iterator,
        collect_inodes=args.hardlinks,
        error_cb="print_stderr",
        #log_cb="print_stderr"
    ):
        handle_dupe_set(dupe_set, hardlinks=args.hardlinks)


if __name__ == "__main__":
    main()
