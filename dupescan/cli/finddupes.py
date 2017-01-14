import argparse
import os
import sys
import time

from dupescan import (
    core,
    criteria,
    fs,
    funcutil,
    log,
    platform,
    report,
    units,
)
from dupescan.cli._common import add_common_cli_args


__all__ = ("execute_report", "scan", "run")


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

    p.add_argument("-o", "--only-mixed-roots",
        action="store_true",
        help="""Only show duplicate files if they arise from recursing into
                different root directories. This can speed operations if the
                only results of interest are whether duplicates exist between
                different filesystem hierarchies, rather than within a single
                one. Note that this only has a useful effect if -r/--recurse
                is specified and two or more paths are provided. If -r/--recurse
                is not specified, this option has no effect. If -r/--recurse
                is specified with only one path, no output will be
                produced."""
    )

    p.add_argument("-m", "--min-size",
        type=units.parse_byte_count,
        default=None,
        metavar="SIZE",
        help="""Ignore files smaller than %(metavar)s. This option accepts a
                byte count. The default is 1."""
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

    p.add_argument("--progress",
        action="store_true",
        help="""Show progress bars on STDERR."""
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

    add_common_cli_args(p)

    return p


def main():
    """Entry point for finddupes command.
    
    Returns:
        Exit code for passing to sys.exit()
    """
    return run(sys.argv[1:])


def run(argv=None):
    """Run finddupes with the specified command line arguments.
    
    Args:
        argv (list of str or None): command line arguments, not including the
            command itself (argv[0]).
    
    Returns:
        Exit code for passing to sys.exit()
    """

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
        config = ScanConfig()
        if args.zero:
            if args.min_size > 0:
                print("Conflicting arguments: --zero implies --min-size 0, but --min-size was also specified.")
                return 1
            config.min_file_size = 0
        elif args.min_size != None:
            config.min_file_size = args.min_size

        if args.dry_run:
            print("Warning: -n/--dry-run has no effect if -x/--execute is not specified.", file=sys.stderr)

        if len(args.paths) == 0:
            print("No paths specified")
            return 1

        config.recurse = args.recurse
        config.only_mixed_roots = args.only_mixed_roots
        config.include_symlinks = args.symlinks
        config.report_hardlinks = args.aliases
        config.prefer = args.prefer
        config.verbose = args.verbose
        config.progress = args.progress
        config.buffer_size = args.buffer_size
        config.log_time = args.time

        scan(args.paths, config)

        return 0

    else:
        if any((
            args.paths,
            args.symlinks,
            args.zero,
            args.aliases,
            args.recurse,
            args.only_mixed_roots,
            args.min_size,
            args.prefer,
            args.time,
            args.progress,
        )):
            print("Only -n/--dry-run can be used with -x/--execute. All other options must be omitted.", file=sys.stderr)
            return 1

        return execute_report(args.execute, args.dry_run)


class ScanConfig(object):
    """Configuration object affecting behavior of the scan() function.

    Attributes:
        recurse (bool): If True, recurse into directories and add all
            descendant files to the set to consider for duplicate detection.

        only_mixed_roots (bool): Only compare files if they were discovered
            by recursing into different root-level directories.

        min_file_size (int): Only consider files whose size in bytes is greater
            or equal to this number.

        include_symlinks (bool): If True, resolve symlinks, otherwise ignore
            them.

        report_hardlinks (bool): If True, go to the effort of detecting
            hardlinks, and call them out in the generated report.

        prefer (str or None): A 'prefer' string expressing how to choose at least
            one file from a set to be marked in the generated report.

        verbose (bool): If True, print debugging info to stderr.

        progress (bool): If True, print progress bars to stderr.

        buffer_size (int): Number of bytes to read at a time when comparing
            files by content.  If 0, the default of
            platform.DEFAULT_BUFFER_SIZE is used.

        log_time (bool): If True, record the amount of time taken and append it
            to the report.
    """
    def __init__(self):
        self.recurse = False
        self.only_mixed_roots = False
        self.min_file_size = 1
        self.include_symlinks = False
        self.report_hardlinks = False
        self.prefer = None
        self.verbose = False
        self.progress = False
        self.buffer_size = 0
        self.log_time = False


def scan(paths, config=None):
    """Run a duplicate scan and generate a report.

    Args:
        paths (iterable of str): The set of files and/or top-level directories
            to search for duplicates.

        config (ScanConfig): A ScanConfig instance that configures various
            aspects of the operation.
    """
    if config is None:
        config = ScanConfig()

    entry_iter = create_file_iterator(paths, config.recurse, config.min_file_size, config.include_symlinks)
    content_indexer = platform.posix_inode if config.report_hardlinks else None # todo: windows hardlink detector
    reporter = create_reporter(config.prefer, config.report_hardlinks)
    logger = log.StreamLogger(
        stream = sys.stderr,
        min_level = log.DEBUG if config.verbose else log.INFO,
    )

    find_dupes = core.DuplicateFinder(
        content_key_func = content_indexer,
        buffer_size = config.buffer_size,
        cancel_func = cancel_if_single_root if config.only_mixed_roots else None,
        logger = logger,
        progress_handler = ProgressHandler(stream=sys.stderr) if config.progress else None,
    )

    start_time = time.time() if config.log_time else 0

    for dupe_set in find_dupes(fs.unique_entries(entry_iter)):
        reporter.handle_dupe_set(dupe_set)

    if config.log_time:
        reporter.print("# Elapsed time: {}".format(units.format_duration(time.time() - start_time)))


def create_file_iterator(paths, recurse=False, min_file_size=1, include_symlinks=False):
    ifunc = (
        fs.recurse_iterator if recurse
        else fs.flat_iterator
    )

    file_size_filter = None
    if min_file_size > 0:
        file_size_filter = lambda e: e.size >= min_file_size

    symlink_filter = None
    if not include_symlinks:
        symlink_filter = lambda e: not e.is_symlink

    file_filter = funcutil.and_of(symlink_filter, file_size_filter)
    dir_filter = symlink_filter

    return ifunc(paths, dir_filter, file_filter)


def cancel_if_single_root(dupe_set):
    roots = set(
        entry.root_index
        for content in dupe_set
        for entry in content.entries
    )

    return len(roots) <= 1


class ProgressHandler(object):
    def __init__(self, stream=None, line_width=78):
        self._line_width = line_width
        self._stream = stream if stream is not None else sys.stderr
        self._last_len = 0

    def progress(self, sets, file_pos, file_size):
        set_vis = "[%s]" % "|".join(str(len(s)) for s in sets)
        read_size = units.format_byte_count(file_size, 0)
        progress_room = self._line_width - (len(set_vis) + len(read_size)) - 2

        if progress_room >= 2:
            progress_chars = int(progress_room * file_pos / file_size + 0.5)
            bar = "".join((
                "*" * progress_chars,
                "-" * (progress_room - progress_chars),
            ))
            line = " ".join((set_vis, bar, read_size))
        else:
            line = " ".join((set_vis, read_size))

        self.set_text(line)

    def clear(self):
        self.set_text("")
        self.set_text("")

    def set_text(self, text):
        effective_text, _, _ = text.partition("\n")
        effective_text = effective_text.replace("\t", "    ")
        effective_text = text[:self._line_width]

        this_len = len(effective_text)
        self._stream.write("\r%s" % effective_text)
        if this_len < self._last_len:
            self._stream.write(" " * (self._last_len - this_len))
        self._stream.flush()
        self._last_len = this_len


def create_reporter(prefer=None, report_hardlinks=False):
    selector = None
    if prefer:
        try:
            selector = criteria.parse_selector(prefer)
        except criteria.ParseError as parse_error:
            for line in highlight_sample(prefer, 78, parse_error.position, parse_error.length):
                print(line, file=sys.stderr)
            raise

    return Reporter(show_hardlink_info=report_hardlinks, selector_func=selector)


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
        self.print("## Size: {file_size} Instances: {inst_count} Excess: {excess_size} Names: {name_count}".format(
            inst_count=len(dupe_set),
            name_count=dupe_set.entry_count,
            file_size=units.format_byte_count(dupe_set.content_size),
            excess_size=units.format_byte_count(dupe_set.total_size - dupe_set.content_size)
        ))

        selected_contents = set()
        if self.selector_func is not None:
            try:
                selected_entries = self.selector_func.pick(dupe_set.all_entries())
            except EnvironmentError as ee:
                self.print("## Skipping selection due to error: {!s}".format(ee))
            else:
                selected_contents.update(select_content_by_entries(dupe_set, selected_entries))

        keep_marker = (
            SELECTION_MARKER_UNIQUE if len(selected_contents) == 1
            else SELECTION_MARKER_NONUNIQUE
        )

        show_hardlink_header = self.show_hardlink_info
        for index, content in enumerate(
            sorted(
                dupe_set,
                key=lambda c: len(c.entries), reverse=True
            )
        ):
            if show_hardlink_header:
                if len(content.entries) == 1:
                    self.print("# Separate instances follow")
                    show_hardlink_header = False
                else:
                    self.print("# Instance {}".format(index + 1))

            for entry in sorted(content.entries, key=lambda e: e.path):
                self.print("{keep_marker} {path}".format(
                    keep_marker=keep_marker if content in selected_contents else " ",
                    path=report.format_path(entry.path)
                ))
        self.print()


def select_content_by_entries(contents, selected_entries):
    selected_paths = frozenset(e.path for e in selected_entries)
    selected_contents = set()

    for content in contents:
        if (
            content not in selected_contents and
            any(entry.path in selected_paths for entry in content.entries)
        ):
            selected_contents.add(content)
            yield content


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


def execute_report(report_path, dry_run):
    errors = False
    with open(report_path, "r") as report_stream:
        for marked, unmarked in report.parse_report(report_stream):
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
