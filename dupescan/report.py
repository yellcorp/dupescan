import ast


__all__ = ("format_path", "parse_path")


class ParseError(Exception):
    pass


def format_path(path):
    return repr(path)


def parse_path(path):
    return ast.literal_eval(path)


def parse_report(stream):
    marked = [ ]
    unmarked = [ ]
    error = False

    for line in stream:
        if line.startswith("#"):
            continue

        if line == "\n":
            if not error and (marked or unmarked):
                yield (tuple(marked), tuple(unmarked))
            marked = [ ]
            unmarked = [ ]
            error = False
            continue

        marker, sep, path = line[0], line[1], parse_path(line[2:].strip())

        if sep != " ":
            # PROBLEM: needs at least one space after marker
            error = True

        elif path == "":
            # PROBLEM: NO PATH
            error = True

        elif marker == " ":
            unmarked.append(path)

        else:
            marked.append(path)

    if not error and (marked or unmarked):
        yield (tuple(marked), tuple(unmarked))
