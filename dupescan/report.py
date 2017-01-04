import re
import unicodedata


__all__ = [ "format_path", "parse_path" ]


CODE_TO_ESCAPE = {
    0x09: "\\t",
    0x0A: "\\n",
    0x0D: "\\r",
    0x5C: "\\\\"
}

ESCAPE_TO_CODE = {
    "t":  0x09,
    "n":  0x0A,
    "r":  0x0D,
    "\\": 0x5C
}

ESCAPE_TO_DIGIT_COUNT = {
    "x": 2,
    "u": 4,
    "U": 8
}

MAX_CODE_TO_FORMAT = (
    (0xff,       "\\x{:02X}"),
    (0xffff,     "\\u{:04X}"),
    (0xffffffff, "\\U{:08X}")
)


BYTES_PREFIX = "\\b"


ESCAPE_CATEGORIES = { "Cc", "Cf", "Cn", "Co", "Cs", "Zl", "Zp", "Zs" }


class ParseError(Exception):
    pass


def hex_escape(n):
    for max_code, format_str in MAX_CODE_TO_FORMAT:
        if n <= max_code:
            return format_str.format(n)
    raise ValueError("Codepoint out of range")


def format_byte(b):
    if b in CODE_TO_ESCAPE:
        return CODE_TO_ESCAPE[b]

    if b < 0x20 or b > 0x7E:
        return hex_escape(b)

    return chr(b)


def format_path_bytes(path):
    return BYTES_PREFIX + "".join(format_byte(b) for b in path)


def format_char(c):
    code = ord(c)
    if code in CODE_TO_ESCAPE:
        return CODE_TO_ESCAPE[code]

    if c != " " and unicodedata.category(c) in ESCAPE_CATEGORIES:
        return hex_escape(code)

    return c


def format_path_str(path):
    return "".join(format_char(c) for c in path)


def escape_surrounding_space(string):
    return re.sub("^ +| +$", lambda m: "\\x20" * len(m.group(0)), string)


def format_path(path):
    if isinstance(path, bytes):
        return escape_surrounding_space(format_path_bytes(path))
    return escape_surrounding_space(format_path_str(path))


def parse_hex_code(string, start, length):
    hex_str = string[start : start + length]
    if len(hex_str) != length:
        raise ParseError("Incomplete hex escape")
    try:
        return int(hex_str, 16)
    except ValueError:
        raise ParseError("Invalid hex escape")


def parse_path(path):
    codes = [ ]
    is_bytes = path.startswith(BYTES_PREFIX)

    index = 2 if is_bytes else 0
    length = len(path)

    while index < length:
        ch = path[index]
        if ch == "\\":
            escape_ch = path[index + 1]
            if escape_ch in ESCAPE_TO_DIGIT_COUNT:
                digit_count = ESCAPE_TO_DIGIT_COUNT[escape_ch]
                codes.append(parse_hex_code(path, index + 2, digit_count))
                index += 2 + digit_count

            elif escape_ch in ESCAPE_TO_CODE:
                codes.append(ESCAPE_TO_CODE[escape_ch])
                index += 2

            else:
                raise ParseError("Invalid escape")
        else:
            codes.append(ord(ch))
            index += 1

    if is_bytes:
        return bytes(codes)

    return "".join(chr(c) for c in codes)


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
