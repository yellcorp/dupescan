import re


def once(func):
    called = False
    value = None
    def f():
        nonlocal called, value
        if not called:
            called = True
            value = func()
        return value
    return f


class ParseError(ValueError):
    pass


_FORMAT_BYTE_SUFFIXES = (" bytes", "K", "M", "G", "T")
def format_byte_count(byte_count, float_precision=1):
    for suffix in _FORMAT_BYTE_SUFFIXES:
        if byte_count < 1024:
            break
        byte_count /= 1024

    if byte_count == int(byte_count):
        float_precision = 0

    return "{value:.{prec}f}{suffix}".format(
        value=byte_count, prec=float_precision, suffix=suffix
    )


_PARSE_BYTE_SUFFIXES = {
    "b": 1,
    "k": 1024,
    "m": 1024**2,
    "g": 1024**3
}

@once
def get_parse_byte_regex():
    return re.compile(
        r"""^
        (?:
            0x (?P<hex> [0-9a-f]+ ) |
            (?P<dec> [0-9]+ )
        )
        \s*
        (?P<suffix> [{suffixes}]? )
        $""".format(suffixes="|".join(_PARSE_BYTE_SUFFIXES.keys())),
        re.IGNORECASE | re.VERBOSE
    )

def parse_byte_count(string):
    match = get_parse_byte_regex().match(string)

    if match is None:
        raise ParseError(string)

    if match.group("hex"):
        value = int(match.group("hex"), 16)
    else:
        value = int(match.group("dec"), 10)

    if match.group("suffix"):
        value *= _PARSE_BYTE_SUFFIXES[match.group("suffix").lower()]

    return value
