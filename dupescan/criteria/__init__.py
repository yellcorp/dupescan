import sys

from dupescan.criteria import parse
from dupescan.criteria._common import ParseError


__all__ = ("ParseError", "parse_selector")


def parse_selector(pref_string):
    return parse.Parser().parse_selector(pref_string)


def main():
    pref_string = sys.argv[1]
    rules = parse_selector(pref_string)
    candidates = sys.argv[2:]
    print(repr(candidates))
    print(repr(rules.pick(candidates)))


if __name__ == "__main__":
    main()
