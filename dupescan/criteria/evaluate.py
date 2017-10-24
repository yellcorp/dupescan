import os
import re

from dupescan import funcutil


class SelectionRules(object):
    def __init__(self, decide_functions):
        self.decide_functions = decide_functions

    def pick(self, candidates):
        this_round = list(candidates)

        for decide in self.decide_functions:
            if len(this_round) < 2:
                break

            next_round = [ this_round.pop(0) ]

            for candidate in this_round:
                outcome = decide(candidate, next_round[0])
                if outcome < 0:
                    next_round = [ candidate ]
                elif outcome == 0:
                    next_round.append(candidate)

            this_round = next_round

        return tuple(this_round)


def build_property_graph(graph):
    for token_sequences, func in (
        (["path"],                        lambda e: e.path),
        (["name"],                        lambda e: e.basename),
        (["dir/ectory"],                  lambda e: e.dirname),
        (["dir/ectory name"],             lambda e: e.parent.basename),
        (["ext/ension"],                  lambda e: e.extension),
        (["mtime", "modification time?"], lambda e: e.mtime),
        (["index"],                       lambda e: e.root.index + 1),
    ):
        prop = EntryProperty(token_sequences, func)
        graph.add(prop.token_sequences, prop)


class EntryProperty(object):
    def __init__(self, token_sequences, func):
        self.token_sequences = tuple(token_sequences)
        self.func = func

    def evaluate(self, entry):
        return self.func(entry)


def build_operator_graph(graph):
    for pos_name, pos_tokens, neg_name, neg_tokens, func, arg_type in (
        ("is",            ["is"],                  "is not",            ["is not", "isnt"],          lambda c, a, b: c.equals(a, b),        None),
        ("contains",      ["contain/s"],           "not contains",      ["not contain/s"],           lambda c, a, b: c.contains(a, b),      str),
        ("starts with",   ["start/s with?"],       "not starts with",   ["not start/s with?"],       lambda c, a, b: c.startswith(a, b),    str),
        ("ends with",     ["end/s with?"],         "not ends with",     ["not end/s with?"],         lambda c, a, b: c.endswith(a, b),      str),
        #("matches glob",  ["match/es glob"],       "not matches glob",  ["not match/es glob"],       ?,                                     str),
        ("matches regex", ["match/es re|regex/p"], "not matches regex", ["not match/es re|regex/p"], lambda c, a, b: c.matches_regex(a, b), str),
    ):
        positive = BinaryFunction(pos_name, pos_tokens, func, arg_type)
        graph.add(positive.token_sequences, positive)
        negative = BinaryFunction(neg_name, neg_tokens, funcutil.not_of(func), arg_type)
        graph.add(negative.token_sequences, negative)


class BinaryFunction(object):
    def __init__(self, name, token_sequences, func, arg_type):
        self.name = name
        self.token_sequences = tuple(token_sequences)
        self.func = func
        self.arg_type = arg_type

    def evaluate(self, context, a, b):
        if self.arg_type is not None:
            bad_messages = [
                "argument {0} is {1!r}".format(index + 1, type(arg))
                for index, arg in enumerate((a, b))
                if not isinstance(arg, self.arg_type)
            ]

            if len(bad_messages) > 0:
                raise ValueError("{me!r} expects type {my_type!r}, but {bads}".format(
                    me=self.name,
                    my_type=self.arg_type,
                    bads=", ".join(bad_messages)
                ))
        return self.func(context, a, b)


def build_adjective_graph(graph):
    for pos_word, neg_word, func, arg_type in (
        ("shorter",   "longer", lambda c, a, b: c.length(a) - c.length(b),               str),
        ("shallower", "deeper", lambda c, a, b: c.count(a, os.sep) - c.count(b, os.sep), str),
        ("earlier",   "later",  lambda c, a, b: c.compare(a, b),                         None),
        ("lower",     "higher", lambda c, a, b: c.compare(a, b),                         None),
    ):
        positive = BinaryFunction(pos_word, [pos_word], func, arg_type)
        graph.add(positive.token_sequences, positive)
        negative = BinaryFunction(neg_word, [neg_word], funcutil.negative_of(func), arg_type)
        graph.add(negative.token_sequences, negative)


def build_modifier_graph(graph):
    graph.add(["ignoring case"], CaseInsensitiveContext())


class CaseSensitiveContext(object):
    def equals(self, a, b):
        return self.compare(a, b) == 0

    def contains(self, a, b):
        return b in a

    def startswith(self, a, b):
        return a.startswith(b)

    def endswith(self, a, b):
        return a.endswith(b)

    def matches_regex(self, a, regex):
        return re.match(regex, a) is not None

    def length(self, a):
        return len(a)

    def count(self, a, string):
        return a.count(string)

    def compare(self, a, b):
        ca, cb = coerce_operands(a, b)
        return compare(ca, cb)


class CaseInsensitiveContext(CaseSensitiveContext):
    def contains(self, a, b):
        return b.lower() in a.lower()

    def startswith(self, a, b):
        return a.lower().startswith(b.lower())

    def endswith(self, a, b):
        return a.lower().endswith(b.lower())

    def matches_regex(self, a, regex):
        return re.match(regex, a, re.IGNORECASE) is not None

    def length(self, a):
        return len(a.lower())

    def count(self, a, string):
        return a.lower().count(string.lower())

    def compare(self, a, b):
        return CaseSensitiveContext.compare(self, lower_if_str(a), lower_if_str(b))


def compare(a, b):
    if a < b:
        return -1
    if a > b:
        return 1
    return 0


def coerce_operands(a, b):
    """Return the two arguments coerced to a common class.

    If one is int, then try to interpret the other as an int as well. If this
    is successful, return both as ints. Otherwise, return both as strs.

    If both are already strs then they are returned unchanged.
    """
    try:
        if isinstance(a, int):
            return a, int(b)
        if isinstance(b, int):
            return int(a), b
    except ValueError:
        pass
    return str(a), str(b)


def lower_if_str(a):
    return a.lower() if isinstance(a, str) else a
