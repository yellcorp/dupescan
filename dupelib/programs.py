import dupelib

import itertools
import os
import sys


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
            file_size=dupelib.unitformat.format_file_size(file_size),
            excess_size=dupelib.unitformat.format_file_size(file_size * (len(dupe_set) - 1))
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
                    path=dupelib.report.format_path(path)
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
        return dupelib.walk.recurse_iterator(paths, dir_filter, file_filter)
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
        selector = dupelib.criteria.parse_selector(prefer)

    return Reporter(show_hardlink_info=report_hardlinks, selector_func=selector)


def finddupes_report(
    paths,
    recurse=False,
    include_empty_files=False,
    include_symlinks=False,
    report_hardlinks=False,
    prefer=None
):
    walker = create_walker(paths, recurse, include_empty_files, include_symlinks)
    reporter = create_reporter(prefer, report_hardlinks)

    for dupe_set in dupelib.find_duplicate_files(
        walker,
        collect_inodes=report_hardlinks,
        error_cb="print_stderr",
        #log_cb="print_stderr"
    ):
        reporter.handle_dupe_set(dupe_set)
