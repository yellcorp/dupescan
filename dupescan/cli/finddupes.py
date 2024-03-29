import argparse
import os
import sys
import time
import traceback
from collections import defaultdict
from typing import Optional, Iterable, Iterator

from dupescan import (
    console,
    core,
    criteria,
    fs,
    funcutil,
    log,
    report,
    units,
)
from dupescan.cli._common import add_common_cli_args, set_encoder_errors
from dupescan.types import AnyPath


__all__ = ("delete_unmarked_in_report", "scan", "run")


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
        help="""List of files to consider. Directories will be recursively
                examined."""
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

    p.add_argument("-o", "--only-mixed-roots",
        action="store_true",
        help="""Only show duplicate files if they arise from recursing into
                different root directories. This can speed operations if the
                only results of interest are whether duplicates exist between
                different filesystem hierarchies, rather than within a single
                one. Note that this only has a useful effect if two or more
                paths are provided."""
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
                the -x/--delete option."""
    )

    p.add_argument("--exclude",
       action="append",
       metavar="NAME",
       help="""Excludes files or directories with the given name. This feature
               is is currently simplified - it only performs case-sensitive
               literal comparisons against a filename - i.e. the last segment
               of the file path. At some point it will be expanded to something
               more like rsync/tar matching."""
    )

    p.add_argument("--time",
        action="store_true",
        help="""Add elapsed time to the generated report."""
    )

    p.add_argument("--help-prefer",
        action="store_true",
        help="""Display detailed help on using the --prefer option"""
    )

    p.add_argument("-v", "--verbose",
        action="store_true",
        help="""Log detailed information to STDERR."""
    )

    p.add_argument("--no-progress",
        dest="progress",
        action="store_false",
        help="""Don't show progress bars on STDERR."""
    )

    p.add_argument("-x", "--delete",
        metavar="PATH",
        help="""Delete unmarked files in the report at %(metavar)s. Sets where
                no files are marked will be skipped."""
    )

    p.add_argument("-c", "--coalesce",
        metavar="PATH",
        help="""Replace duplicate files with hard links, using sets found in
                the report at %(metavar)s. File marks are ignored - all
                filenames are preserved."""
    )

    p.add_argument("-n", "--dry-run",
        action="store_true",
        help="""Used in combination with -x/--delete or -c/--coalesce. List
                actions that those options would perform without actually doing
                them."""
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
    sys.stdout = set_encoder_errors(sys.stdout, "backslashreplace")

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

    if args.delete is not None or args.coalesce is not None:
        if args.delete is not None and args.coalesce is not None:
            print(
                "Conflicting arguments: -x/--delete and -c/--coalesce are mutually exclusive.",
                file=sys.stderr,
            )
            return 1

        if any((
            args.paths,
            args.symlinks,
            args.zero,
            args.only_mixed_roots,
            args.min_size,
            args.prefer,
            args.time,
            args.exclude,
        )):
            print("Only -n/--dry-run can be used with -x/--delete or -c/--coalesce. All other options must be omitted.", file=sys.stderr)
            return 1

        if args.delete is not None:
            return delete_unmarked_in_report(args.delete, args.dry_run, args.verbose)

        hard_linker = HardLinker(args.coalesce, args.dry_run, args.verbose)
        return hard_linker()

    else:
        config = ScanConfig()
        if args.zero:
            if args.min_size is not None and args.min_size > 0:
                print(
                    "Conflicting arguments: --zero implies --min-size 0, but --min-size was also specified.",
                    file=sys.stderr,
                )
                return 1
            config.min_file_size = 0
        elif args.min_size != None:
            config.min_file_size = args.min_size

        if args.dry_run:
            print("Warning: -n/--dry-run has no effect without -x/--delete or -c/--coalesce.", file=sys.stderr)

        if len(args.paths) == 0:
            print("No paths specified", file=sys.stderr)
            return 1

        config.recurse = True
        config.only_mixed_roots = args.only_mixed_roots
        config.include_symlinks = args.symlinks
        config.prefer = args.prefer
        config.verbose = args.verbose
        config.progress = args.progress
        config.max_memory = args.max_memory
        config.max_buffer_size = args.max_buffer_size
        config.log_time = args.time

        if args.exclude:
            config.exclude.extend(args.exclude)

        if config.only_mixed_roots and len(args.paths) <= 1:
            print("Warning: -o/--only-mixed-roots with a single path will not produce any results.", file=sys.stderr)

        scan(args.paths, config)

        return 0


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

        prefer (str or None): A 'prefer' string expressing how to choose at least
            one file from a set to be marked in the generated report.

        verbose (bool): If True, print debugging info to stderr.

        progress (bool): If True, print progress bars to stderr.

        max_memory (int): Adjust buffer size and maximum number of open files so
            as not to exceed this many bytes.  This will be exceeded if set
            below platform.MIN_BUFFER_SIZE.  If 0, the default of
            platform.DEFAULT_MAX_MEMORY is used.

        max_buffer_size (int): Absolute maximum buffer size.  This will always
            be imposed even if max_memory allows a bigger buffer size.  If 0,
            the default of platform.DEFAULT_MAX_BUFFER_SIZE is used.

        log_time (bool): If True, record the amount of time taken and append it
            to the report.

        exclude (List[str]): List of names to exclude.
    """
    def __init__(self):
        self.recurse = False
        self.only_mixed_roots = False
        self.min_file_size = 1
        self.include_symlinks = False
        self.prefer = None
        self.verbose = False
        self.progress = False
        self.max_buffer_size = 0
        self.max_memory = 0
        self.log_time = False
        self.exclude = []


def scan(paths: Iterable[AnyPath], config: Optional[ScanConfig]=None):
    """Run a duplicate scan and generate a report.

    Args:
        paths (iterable of Path): The set of files and/or top-level directories
            to search for duplicates.

        config (ScanConfig): A ScanConfig instance that configures various
            aspects of the operation.
    """
    if config is None:
        config = ScanConfig()

    logger = log.StreamLogger(
        stream = sys.stderr,
        min_level = log.DEBUG if config.verbose else log.INFO,
    )

    entries = create_file_iterator(
        paths,
        logger,
        config.recurse,
        config.exclude,
        config.min_file_size,
        config.include_symlinks
    )
    reporter = create_reporter(config.prefer)

    if config.progress:
        try:
            use_unicode = sys.stderr.encoding in ("utf_8",)
        except AttributeError:
            use_unicode = False

        compare_progress_handler = CompareProgressHandler(
            glyphs = use_unicode,
            stream = sys.stderr,
        )

        walk_progress_handler = WalkProgressHandler(stream=sys.stderr)
    else:
        walk_progress_handler = None
        compare_progress_handler = None

    find_dupes = core.DuplicateFinder(
        max_memory = config.max_memory,
        max_buffer_size = config.max_buffer_size,
        cancel_func = cancel_if_single_root if config.only_mixed_roots else None,
        logger = logger,
        compare_progress_handler = compare_progress_handler,
        walk_progress_handler = walk_progress_handler,
    )

    start_time = time.time() if config.log_time else 0

    for dupe_set in find_dupes(entries):
        reporter.handle_dupe_set(dupe_set)

    if config.log_time:
        print("# Elapsed time: %s" % units.format_duration(time.time() - start_time))


def create_file_iterator(
        paths: Iterable[AnyPath],
        logger=None,
        recurse=False,
        exclude: Optional[Iterable[str]]=None,
        min_file_size=1,
        include_symlinks=False
) -> Iterator[fs.FileEntry]:
    if logger is not None:
        def onerror(env_error):
            logger.error(str(env_error))
    else:
        def onerror(_):
            pass

    ifunc = (
        fs.recurse_iterator if recurse
        else fs.flat_iterator
    )

    name_filter = None
    if exclude:
        exclude_set = frozenset(exclude)
        name_filter = lambda e: e.basename not in exclude_set

    file_size_filter = None
    if min_file_size > 0:
        file_size_filter = lambda e: e.size >= min_file_size

    symlink_filter = None
    if not include_symlinks:
        symlink_filter = lambda e: not e.is_symlink

    file_filter = funcutil.and_of(name_filter, funcutil.and_of(symlink_filter, file_size_filter))
    dir_filter = name_filter

    return ifunc(paths, dir_filter, file_filter, onerror)


def cancel_if_single_root(dupe_set):
    index = -1

    for entry in dupe_set.all_entries():
        if index == -1:
            index = entry.root.index
        elif index != entry.root.index:
            return False

    return True


class WalkProgressHandler(object):
    def __init__(self, stream=None, line_width=78):
        self._status_line = console.StatusLine(
            stream = stream if stream is not None else sys.stderr,
            line_width = line_width,
            elide_string = ".."
        )

    def progress(self, path):
        self._status_line.set_text(path)

    def complete(self):
        self._status_line.clear()


GLYPHS = {
    "ascii": ("#-", ""),
    "unicode": (
        "\u2588\u2591",
        "\u2800\u2840\u28C0\u28C4\u28E4\u28E6\u28F6\u28F7\u28FF"
    )
}
class CompareProgressHandler(object):
    def __init__(self, glyphs=True, stream=None, line_width=78):
        self._status_line = console.StatusLine(
            stream = stream if stream is not None else sys.stderr,
            line_width = line_width
        )

        if glyphs is True:
            glyphs = GLYPHS["unicode"]
        elif glyphs is False:
            glyphs = GLYPHS["ascii"]

        self._progress_glyphs, self._count_glyphs = glyphs

    def progress(self, sets, file_pos, file_size):
        set_vis_list = [ ]
        for s in sets:
            set_len = len(s)
            if set_len >= len(self._count_glyphs):
                set_vis_list.append(str(set_len))
            else:
                set_vis_list.append(self._count_glyphs[set_len])

        set_vis = "[%s]" % "|".join(set_vis_list)
        read_size = units.format_byte_count(file_size, 0)
        progress_room = self._status_line.line_width - (len(set_vis) + len(read_size)) - 2

        if progress_room >= 2:
            if file_size > 0:
                progress_chars = int(progress_room * file_pos / file_size + 0.5)
            else:
                progress_chars = progress_room

            bar = "".join((
                self._progress_glyphs[0] * progress_chars,
                self._progress_glyphs[1] * (progress_room - progress_chars),
            ))
            line = " ".join((set_vis, bar, read_size))
        else:
            line = " ".join((set_vis, read_size))

        self._status_line.set_text(line)

    def clear(self):
        self._status_line.clear()


def create_reporter(prefer=None):
    selector = None

    formatter = report.ReportFormatter()

    if prefer:
        try:
            selector = criteria.parse_selector(prefer)
        except criteria.ParseError as parse_error:
            for line in highlight_sample(prefer, 78, parse_error.position, parse_error.length):
                print(line, file=sys.stderr)
            raise

    return Reporter(formatter, selector=selector)


class Reporter(object):
    def __init__(self, formatter, selector=None, output_stream=None):
        self._formatter = formatter
        self._selector = selector
        self._output_stream = output_stream or sys.stdout

    def handle_dupe_set(self, dupe_set):
        header = [
            "Size: {inst_size} Instances: {inst_count} Excess: {excess_size} Names: {name_count}".format(
                inst_size = units.format_byte_count(dupe_set.instance_size),
                inst_count = len(dupe_set),
                excess_size = units.format_byte_count(dupe_set.total_size - dupe_set.instance_size),
                name_count = dupe_set.entry_count,
            )
        ]

        # selection is done by entry
        preferred_entries = set()
        if self._selector is not None:
            try:
                preferred_entries.update(self._selector.pick(dupe_set.all_entries()))
            except EnvironmentError as env_error:
                header.append("Skipping selection due to error: %s" % env_error)

        # but to test uniqueness, we go by content. for example, it's
        # considered unique if multiple entries are returned, but they
        # point to the one instance
        selected_instances = set(
            instance for instance in dupe_set
            if any(entry in preferred_entries for entry in instance.entries)
        )

        # if an instance has any of its entries marked, mark the others as well
        for instance in selected_instances:
            preferred_entries.update(instance.entries)

        for line in self._formatter.format_set(
            dupe_set,
            preferred_entries,
            header,
        ):
            print(line, file=self._output_stream)


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


def delete_unmarked_in_report(report_path, dry_run, verbose):
    verbose = verbose or dry_run
    errors = False
    with open(report_path, "r") as report_stream:
        for dupe_set, marked_entries in report.parse_report(report_stream):
            if len(marked_entries) > 0:
                for entry in dupe_set.all_entries():
                    if entry in marked_entries:
                        continue
                    
                    if verbose:
                        print(entry.path, end="")

                    try:
                        if not dry_run:
                            os.remove(entry.path)
                        if verbose:
                            print()
                    except EnvironmentError as env_error:
                        if not verbose:
                            print(entry.path, end="")
                        print(": %s" % env_error)
                        errors = True

    return 2 if errors else 0


class HardLinker(object):
    def __init__(self, report_path, dry_run, verbose):
        self._report_path = report_path
        self._verbose = verbose or dry_run
        self._commit = not dry_run

    def __call__(self):
        with open(self._report_path, "r") as report_stream:
            for dupe_set, _ in report.parse_report(report_stream):
                self._link_entries(dupe_set.all_entries())

    def _link_entries(self, entries):
        sizes = defaultdict(list)
        linkables = defaultdict(list)
        candidate_count = 0
        linked_count = 0
        representative = None

        for entry in entries:
            try:
                if entry.is_symlink or not entry.is_file:
                    continue
                if representative is None:
                    representative = entry
                link_key = self._hardlink_key(entry)
                linkables[link_key].append(entry)
                sizes[entry.size].append(entry)
                candidate_count += 1
            except OSError:
                print('Could not index {!r}'.format(entry), file=sys.stderr)
                x_type, x_value, x_tb = sys.exc_info()
                traceback.print_exception(x_type, x_value, None, file=sys.stderr)
                continue

        if len(sizes) > 1:
            print(
                'In group containing {!r}: Not proceeding because file sizes are inconsistent. Report is probably out of date and needs to be rerun.'.format(
                    representative.path,
                    linked_count,
                    candidate_count,
                    len(linkables),
                ),
                file=sys.stderr,
            )
            return

        for compatible_entries in linkables.values():
            if len(compatible_entries) > 1:
                link_success = 0
                compatible_entries.sort(key=lambda entry: entry.mtime)
                prototype = compatible_entries.pop()
                for entry in compatible_entries:
                    ok = True
                    if self._verbose:
                        print('{!r} = {!r}'.format(entry.path, prototype.path))

                    if self._commit and prototype.uid != entry.uid:
                        try:
                            self._replace_with_link(prototype, entry)
                        except OSError:
                            print(
                                'Could not replace {!r} with link to {!r}'.format(
                                    entry.path,
                                    prototype.path
                                ),
                                file=sys.stderr
                            )
                            x_type, x_value, x_tb = sys.exc_info()
                            traceback.print_exception(x_type, x_value, None, file=sys.stderr)
                            ok = False

                    if ok:
                        link_success += 1

                if link_success > 0:
                    linked_count += link_success + 1

        if linked_count < candidate_count or len(linkables) > 1:
            print(
                'In group containing {!r}: Failed to coalesce all instances: Linked {} of {}, Instance count {}'.format(
                    representative.path,
                    linked_count,
                    candidate_count,
                    len(linkables),
                ),
                file=sys.stderr,
            )

    def _replace_with_link(self, prototype, entry):
        safety_new = self._unique_name('new', entry.dirname, entry.barename, entry.extension)
        safety_old = self._unique_name('old', entry.dirname, entry.barename, entry.extension)

        danger = False

        os.link(prototype.path, safety_new)
        try:
            os.link(entry.path, safety_old)

            os.unlink(entry.path)
            danger = True

            os.link(safety_new, entry.path)
            danger = False
        except OSError:
            if danger > 0:
                os.link(safety_old, entry.path)
                danger = True
            raise
        finally:
            if not danger:
                os.unlink(safety_old)
            os.unlink(safety_new)

    def _hardlink_key(self, entry):
        entry_stat = entry.stat
        return (
            entry_stat.st_dev,
            entry_stat.st_size,
            entry_stat.st_mode,
            entry_stat.st_uid,
            entry_stat.st_gid,
            entry_stat.st_flags,
        )

    def _unique_name(self, namespace, dirname, stem, extension):
        counter = 0
        while True:
            upath = os.path.join(
                dirname,
                '{}^{}^{}{}'.format(stem, namespace, counter, extension)
            )

            if not os.path.lexists(upath):
                return upath

            counter += 1
