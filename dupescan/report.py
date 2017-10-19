import ast
import re

from dupescan import (
    core,
    fs,
)


__all__ = (
    "ParseError",
    "parse_report",
    "ReportFormatter",
)


class ParseError(Exception):
    pass


PATH_LINE_PATTERN = re.compile(r"""^([!$-/:-@\[\]-`{-~]?\s*)?b?['"]""")
NONE = 0
PATH = 1
KEYWORD = 2


def parse_line(line, line_num):
    sline = line.strip()
    if sline == "" or sline[0] == "#":
        return NONE, None

    path_match = PATH_LINE_PATTERN.match(sline)

    if path_match is not None:
        prefix = path_match.group(1)
        path_repr = sline[len(prefix):]
        try:
            path = ast.literal_eval(path_repr)
        except SyntaxError:
            raise ParseError("Bad string", line_num + 1)

        marked = len(prefix) > 0 and prefix[0] not in "\t \"'b"
        return PATH, (marked, path)

    keyword, _, _ = sline.partition("#")
    return KEYWORD, keyword.rstrip().lower()


def parse_report(line_iter):
    current_set = None
    current_instance = None
    marked_entries = set()

    singleton_mode = False

    def end_instance():
        nonlocal current_set, current_instance
        if current_instance:
            #if current_set is None:
            #    raise ParseError("")
            current_set.append(fs.FileInstance(address=None, entries=current_instance))
        current_instance = [ ]

    def end_set():
        nonlocal current_set, marked_entries
        if current_set:
            yield core.DuplicateInstanceSet(current_set), marked_entries
        current_set = [ ]
        marked_entries = set()

    for line_num, line in enumerate(line_iter):
        line_type, line_data = parse_line(line, line_num)

        if line_type == NONE:
            continue

        if current_set is None:
            if line_type != KEYWORD or line_data != "set":
                raise ParseError("Expected 'Set'", line_num + 1)

        if line_type == KEYWORD:
            if line_data == "set":
                end_instance()
                yield from end_set()
                singleton_mode = True

            elif line_data == "instance":
                end_instance()
                singleton_mode = False

            elif line_data == "singletons":
                end_instance()
                singleton_mode = True

            else:
                raise ParseError("Bad keyword: %s" % line_data, line_num + 1)

        else:
            marked, path = line_data
            entry = fs.FileEntry.from_path(path)
            current_instance.append(entry)
            if marked:
                marked_entries.add(entry)
            if singleton_mode:
                end_instance()

    end_instance()
    yield from end_set()


def single_marked_instance(instances, marked_entries):
    count = 0
    for instance in instances:
        if any(entry in marked_entries for entry in instance.entries):
            count += 1
            if count == 2:
                return False
    return count == 1


class ReportFormatter(object):
    def __init__(self, mark_glyphs = (">", "?")):
        self._mark_glyphs = mark_glyphs

    def format_set(
        self,
        dupe_set,
        marked_entries = None,
        header_comment_lines = None
    ):
        line = [ "Set" ]
    
        hcl = [ ]
        if header_comment_lines is None:
            hcl.extend(header_comment_lines)
    
        if len(header_comment_lines) > 0:
            line.append(" # %s" % header_comment_lines[0])
        yield "".join(line)
    
        for header_comment_line in header_comment_lines[1:]:
            yield "# %s" % header_comment_line
    
        if marked_entries is None:
            marked_entries = set()
    
        instances = list(sorted(
            dupe_set,
            key = lambda i: len(i.entries),
            reverse = True,
        ))
    
        mark_glyph = self._mark_glyphs[
            0 if single_marked_instance(instances, marked_entries) else 1
        ]

        show_instance_info = True
        for index, instance in enumerate(instances):
            if show_instance_info:
                if len(instance.entries) == 1:
                    yield " Singletons # Separate instances follow"
                    show_instance_info = False
                else:
                    yield " Instance # %d" % (index + 1)
    
            for entry in sorted(instance.entries, key=lambda entry: entry.path):
                glyph = mark_glyph if entry in marked_entries else " "
                yield "%s %r" % (glyph, entry.path)
    
        yield ""
