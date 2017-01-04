import dupescan

import argparse
import itertools
import os
import sys
import time


__all__ = [ "execute_report", "scan", "run" ]


SIZE_NOT_SET = -1

def get_arg_parser():
    p = argparse.ArgumentParser(
        description="Find files with identical content.",
        epilog="""Arguments that accept byte counts accept an integer with an
                  optional suffix indicating units.  'B' indicates bytes, which
                  is also the default if no suffix is provided.  'K' indicates
                  kibibytes (1024 bytes).  'M' indicates mebibytes.  'G'
                  indicates gibibytes, and 'T' indicates tebibytes."""
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
                to have identical content. This option is equivalent to
                --min-size 0"""
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

    p.add_argument("-m", "--min-size",
        type=dupescan.units.parse_byte_count,
        default=SIZE_NOT_SET,
        metavar="SIZE",
        help="""Ignore files smaller than %(metavar)s. This option accepts a
                byte count. The default is 1."""
    )

    p.add_argument("--buffer-size",
        type=dupescan.units.parse_byte_count,
        default=SIZE_NOT_SET,
        metavar="SIZE",
        help="""Specifies the size of each buffer used when comparing files by
                content. This option accepts a byte count.  The default is
                4096."""
    )

    p.add_argument("-p", "--prefer",
        metavar="CRITERIA",
        help="""For each set of duplicate files, automatically select one
                for preservation according to the provided criteria. Other
                duplicates can be deleted by passing the generated report to
                the -x/--execute option."""
    )

    p.add_argument("--time",
        action="store_true",
        help="""Add elasped time to the generated report."""
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

    p.add_argument("--version",
        action="version",
        version="%(prog)s " + dupescan.__version__
    )

    return p


SELECTION_MARKER_UNIQUE =    ">"
SELECTION_MARKER_NONUNIQUE = "?"
class Reporter(object):
    def __init__(self, show_hardlink_info=True, selector_func=None, output_stream=sys.stdout):
        self.show_hardlink_info = show_hardlink_info
        self.selector_func = selector_func
        self.output_stream = output_stream

    def print(self, *args):
        print(*args, file=self.output_stream)

    def handle_dupe_set(self, dupe_set):
        file_size = os.stat(dupe_set[0].path()).st_size

        self.print("## Size: {file_size} Instances: {inst_count} Excess: {excess_size} Names: {name_count}".format(
            inst_count=len(dupe_set),
            name_count=sum(len(instance.paths) for instance in dupe_set),
            file_size=dupescan.units.format_byte_count(file_size),
            excess_size=dupescan.units.format_byte_count(file_size * (len(dupe_set) - 1))
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
                self.print("## Skipping selection due to error: {!s}".format(ee))

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
                    self.print("# Separate instances follow")
                    instance_header = False
                else:
                    self.print("# Instance {}".format(index + 1))

            for path in sorted(instance.paths):
                self.print("{keep_marker} {path}".format(
                    keep_marker=keep_marker if instance in selected_instances else " ",
                    path=dupescan.report.format_path(path)
                ))
        self.print()


def and_funcs(f, g):
    if f is None:
        return g
    if g is None:
        return f

    def h(a):
        return f(a) and g(a)
    return h


def create_walker(paths, recurse=False, min_file_size=1, include_symlinks=False):
    file_size_filter = None
    if min_file_size > 0:
        file_size_filter = lambda f: os.stat(f).st_size >= min_file_size

    symlink_filter = None
    if not include_symlinks:
        symlink_filter = lambda f: not os.path.islink(f)

    file_filter = and_funcs(symlink_filter, file_size_filter)
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


def highlight_sample(sample, line_width, hl_pos, hl_length):
    if hl_pos is None:
        return

    highlight_buf = [ " " * hl_pos ]
    max_length = line_width - 12
    if hl_length is None:
        highlight_buf.append("^")
        hl_length = max_length
    else:
        highlight_buf.append("~" * hl_length)
        hl_length = min(hl_length, max_length)
    highlight = "".join(highlight_buf)

    start = hl_pos - int((line_width - hl_length) / 2)
    if start <= 0:
        start = 0
        start_ellipsis = False
    else:
        start_ellipsis = True

    end_ellipsis = start + line_width < len(sample)
    sample = sample[start : start + line_width]
    if start_ellipsis:
        sample = "..." + sample[3:]
    if end_ellipsis:
        sample = sample[:-3] + "..."
    yield sample

    highlight = highlight[start : start + line_width]
    yield highlight


def create_reporter(prefer=None, report_hardlinks=False):
    selector = None
    if prefer:
        try:
            selector = dupescan.criteria.parse_selector(prefer)
        except dupescan.criteria.ParseError as parse_error:
            for line in highlight_sample(prefer, 78, parse_error._position, parse_error._length):
                print(line, file=sys.stderr)
            raise

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
    min_file_size=1,
    include_symlinks=False,
    report_hardlinks=False,
    prefer=None,
    verbose=False,
    buffer_size=0,
    log_time=False
):
    walker = create_walker(paths, recurse, min_file_size, include_symlinks)
    reporter = create_reporter(prefer, report_hardlinks)

    start_time = time.time() if log_time else 0

    for dupe_set in dupescan.find_duplicate_files(
        walker,
        collect_inodes=report_hardlinks,
        error_cb="print_stderr",
        log_cb="print_stderr" if verbose else None,
        buffer_size=buffer_size
    ):
        reporter.handle_dupe_set(dupe_set)

    if log_time:
        reporter.print("# Elapsed time: {}".format(dupescan.units.format_duration(time.time() - start_time)))


def run(argv=None):
    p = get_arg_parser()
    args = p.parse_args(argv)

    if args.help_prefer:
        with open(
            os.path.join(
                os.path.abspath(os.path.dirname(__file__)),
                "preferhelp"
            )
        ) as stream:
            print(stream.read().format(script_name=os.path.basename(sys.argv[0])))
        return 0

    if args.execute is None:
        min_file_size = 1
        if args.zero:
            if args.min_size > 0:
                print("Conflicting arguments: --zero implies --min-size 0, but --min-size was also specified.")
                return 1
            min_file_size = 0
        elif args.min_size != SIZE_NOT_SET:
            min_file_size = args.min_size

        if args.dry_run:
            print("Warning: -n/--dry-run has no effect if -x/--execute is not specified.", file=sys.stderr)
        scan(
            paths=args.paths,
            recurse=args.recurse,
            min_file_size=min_file_size,
            include_symlinks=args.symlinks,
            report_hardlinks=args.aliases,
            prefer=args.prefer,
            verbose=args.verbose,
            buffer_size=args.buffer_size,
            log_time=args.time
        )
        return 0

    else:
        if (
            any(s != SIZE_NOT_SET for s in (args.min_size, args.buffer_size)) or
            any((
                args.paths,
                args.symlinks,
                args.zero,
                args.aliases,
                args.recurse,
                args.prefer,
                args.buffer_size,
                args.time
            ))
        ):
            print("Only -n/--dry-run can be used with -x/--execute. All other options must be omitted.", file=sys.stderr)
            return 1

        return execute_report(args.execute, args.dry_run)


def main():
    return run(sys.argv[1:])
