import os
import re
import sys


class ParseError(Exception):
    def __init__(self, message, position=None, length=None):
        Exception.__init__(self, message, position, length)
        self.message = message
        self.position = position
        self.length = length

    @classmethod
    def create_from_token(cls, message, token):
        return cls(message, token.position, len(token.text))

    def __str__(self):
        buf = [ self.message ]
        if self.position is not None:
            buf.append(" at position {}".format(self.position))
            if self.length is not None and self.length > 1:
                buf.append("-{}".format(self.position + self.length - 1))
        return "".join(buf)


class TokenGraph(object):
    class Node(object):
        def __init__(self):
            self.accept = False
            self.out_edges = { }
            self.data = None

        def join(self, label):
            if label not in self.out_edges:
                self.out_edges[label] = TokenGraph.Node()
            return self.out_edges[label]

    class Navigator(object):
        def __init__(self, node):
            self.node = node

        def can_go(self, token):
            return token.is_string() and token.value in self.node.out_edges

        def go(self, token):
            if self.can_go(token):
                self.node = self.node.out_edges[token.value]
            else:
                raise ParseError.create_from_token("Unexpected token", token)

        def accept(self):
            return self.node.accept

        def data(self):
            if self.accept():
                return self.node.data
            raise ParseError("Non-accepting state")

        def edges(self):
            edges = [ None ] if self.node.accept else [ ]
            edges.extend(self.node.out_edges.keys())
            return edges

    def __init__(self):
        self.root = TokenGraph.Node()

    def add(self, paths, data):
        for path in paths:
            self._add_path(path, data)

    def _add_path(self, path, data):
        current_nodes = [ self.root ]
        tokens = path.split(" ")

        for token in tokens:
            next_nodes = [ ]

            if token.endswith("?"):
                token = token[:-1]
                next_nodes.extend(current_nodes)

            alts = token.split("|")
            for alt in alts:
                suffixes = alt.split("/")
                prefix = suffixes[0]
                suffixes[0] = ""

                for suffix in suffixes:
                    for node in current_nodes:
                        next_nodes.append(node.join(prefix + suffix))

            current_nodes = next_nodes

        for node in current_nodes:
            node.accept = True
            node.data = data

    def navigator(self):
        return TokenGraph.Navigator(self.root)


class EntryProperty(object):
    def __init__(self, token_sequences, func):
        self.token_sequences = tuple(token_sequences)
        self.func = func

    def evaluate(self, entry):
        return self.func(entry)

def build_property_graph():
    graph = TokenGraph()

    for token_sequences, func in (
        (["path"],                        lambda p: p.path),
        (["name"],                        lambda p: p.basename),
        (["dir/ectory"],                  lambda p: p.parent.path),
        (["dir/ectory name"],             lambda p: p.parent.path.basename),
        (["ext/ension"],                  lambda p: p.extension),
        (["mtime", "modification time?"], lambda p: p.mtime),
        (["index"],                       lambda p: p.root_index + 1),
    ):
        prop = EntryProperty(token_sequences, func)
        graph.add(prop.token_sequences, prop)

    return graph


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


def compose_not(f):
    def g(*args):
        return not f(*args)
    return g


def build_operator_graph():
    graph = TokenGraph()

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
        negative = BinaryFunction(neg_name, neg_tokens, compose_not(func), arg_type)
        graph.add(negative.token_sequences, negative)

    return graph


def compare(a, b):
    if a < b:
        return -1
    if a > b:
        return 1
    return 0


def compose_negate(f):
    def g(*args):
        return -f(*args)
    return g


def build_adjective_graph():
    graph = TokenGraph()

    for pos_word, neg_word, func, arg_type in (
        ("shorter",   "longer", lambda c, a, b: c.length(a) - c.length(b),               str),
        ("shallower", "deeper", lambda c, a, b: c.count(a, os.sep) - c.count(b, os.sep), str),
        ("earlier",   "later",  lambda c, a, b: c.compare(a, b),                         None),
        ("lower",     "higher", lambda c, a, b: c.compare(a, b),                         None),
    ):
        positive = BinaryFunction(pos_word, [pos_word], func, arg_type)
        graph.add(positive.token_sequences, positive)
        negative = BinaryFunction(neg_word, [neg_word], compose_negate(func), arg_type)
        graph.add(negative.token_sequences, negative)

    return graph


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

        if ca < cb:
            return -1
        if ca > cb:
            return 1
        return 0


def lower_if_str(a):
    return a.lower() if isinstance(a, str) else a

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


def build_modifier_graph():
    graph = TokenGraph()
    graph.add(["ignoring case"], CaseInsensitiveContext())
    return graph


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


class Token(object):
    STRING = 1
    COMMA = 2
    END = 3

    _type_names = {
        STRING: "string",
        COMMA:  "comma",
        END:    "end"
    }

    def __init__(self, token_type, value, text, position):
        self.token_type = token_type
        self.value = value
        self.text = text
        self.position = position

    def __repr__(self):
        return "Token({})".format(
            ", ".join(repr(a) for a in (
                self.token_type,
                self.value,
                self.text,
                self.position,
            ))
        )

    __str__ = __repr__

    def type_name(self):
        return self._type_names.get(self.token_type, "<bad type>")

    def is_type(self, token_type):
        return self.token_type == token_type

    def is_string(self, value=None):
        return self.token_type == self.STRING and (
            value is None or
            self.value == value
        )


ESCAPES = {
    "0": chr(0),
    "b": "\b",
    "f": "\f",
    "n": "\n",
    "r": "\r",
    "t": "\t"
}
def translate_escape(ch):
    if ch in ESCAPES:
        return ESCAPES[ch]
    return ch


class Lexer(object):
    def __init__(self):
        self.text = None
        self.pos = 0
        self._len = 0
        self._start = 0

    def start(self, text):
        self.text = str(text)
        self.pos = 0
        self._len = len(self.text)
        self._start = 0

    def next_token(self):
        self._start = self.pos
        while self.pos < self._len:
            ch = self.text[self.pos]
            if ch.isspace():
                self.pos += 1
                continue

            if ch == ",":
                self.pos += 1
                return self._token(Token.COMMA, None)
            elif ch in "'\"":
                return self._quoted_string()
            else:
                return self._bare_string()
        return Token(Token.END, None, "", self.pos)

    def _token(self, token_type, value):
        return Token(token_type, value, self.text[self._start : self.pos], self._start)

    def _bare_string(self):
        value = [ ]
        while self.pos < self._len:
            ch = self.text[self.pos]
            if ch.isspace() or ch == ",":
                break
            self.pos += 1
            if ch == "\\":
                value.append(self._escape_char())
            else:
                value.append(ch)
        return self._token(Token.STRING, "".join(value))

    def _quoted_string(self):
        value = [ ]
        quote = self.text[self.pos]
        assert quote in "'\""
        self.pos += 1
        while self.pos < self._len:
            ch = self.text[self.pos]
            self.pos += 1
            if ch == quote:
                return self._token(Token.STRING, "".join(value))
            if ch == "\\":
                value.append(self._escape_char())
            else:
                value.append(ch)
        raise ParseError("Unterminated quoted string", self._start, self._len - self._start)

    def _escape_char(self):
        start = self.pos
        if self.pos < self._len:
            ch = self.text[self.pos]
            self.pos += 1
            if ch == "x":
                return self._hex_escape(2)
            if ch == "u":
                return self._hex_escape(4)
            if ch == "U":
                return self._hex_escape(6)
            return translate_escape(ch)
        raise ParseError("Incomplete escape", start, self._len - start)

    def _hex_escape(self, char_count):
        start = self.pos
        text = self.text[self.pos : self.pos + char_count]
        self.pos += char_count
        if len(text) != char_count:
            raise ParseError("Incomplete escape", start, self._len - start)
        try:
            return chr(int(text, 16))
        except ValueError as ve:
            raise ParseError("Invalid hex escape", start, self._len - start) from ve


class Parser(object):
    _property_graph = build_property_graph()
    _operator_graph = build_operator_graph()
    _adjective_graph = build_adjective_graph()
    _modifier_graph = build_modifier_graph()

    def __init__(self):
        self._lex = Lexer()
        self._token = None

    def _error_expected(self, expected_tokens):
        expected_tokens = list(expected_tokens)
        if len(expected_tokens) == 1:
            expected_desc = expected_tokens[0]
        else:
            expected_desc = "one of {}".format(", ".join(expected_tokens))

        raise ParseError.create_from_token(
            "Expected {}".format(expected_desc),
            self._token
        )

    def _consume(self):
        self._token = self._lex.next_token()

    def parse_selector(self, text):
        self._lex.start(text)
        self._consume()

        criteria = self._criteria()
        return SelectionRules(criteria)

    def _criteria(self):
        criteria = [ ]
        while True:
            criteria.append(self._criterion())

            if self._token.is_type(Token.END):
                return criteria
            elif self._token.is_type(Token.COMMA):
                self._consume()
            else:
                self._error_expected(("','", "end"))

    def _criterion(self):
        prop_nav = self._property_graph.navigator()
        adj_nav = self._adjective_graph.navigator()

        if prop_nav.can_go(self._token):
            return self._boolean_statement()

        if adj_nav.can_go(self._token):
            return self._comparative_statement()

        self._error_expected(repr(t) for t in (prop_nav.edges() + adj_nav.edges()))

    def _boolean_statement(self):
        prop = self._property()
        op = self._operator()
        arg = self._argument()
        context = self._modifier()

        def evaluate(entry):
            return op.evaluate(
                context,
                prop.evaluate(entry),
                arg
            )

        def comparator(a, b):
            return int(evaluate(b)) - int(evaluate(a))

        return comparator

    def _comparative_statement(self):
        adj = self._adjective()
        prop = self._property()
        context = self._modifier()

        def comparator(a, b):
            return adj.evaluate(
                context,
                prop.evaluate(a),
                prop.evaluate(b)
            )

        return comparator

    def _property(self):
        return self._parse_using(self._property_graph)

    def _operator(self):
        return self._parse_using(self._operator_graph)

    def _adjective(self):
        return self._parse_using(self._adjective_graph)

    def _modifier(self):
        if self._modifier_graph.navigator().can_go(self._token):
            return self._parse_using(self._modifier_graph)
        return CaseSensitiveContext()

    def _argument(self):
        if self._token.is_string():
            val = self._token.value
            self._consume()
            return val
        self._error_expected(("string",))

    def _parse_using(self, graph):
        nav = graph.navigator()
        while nav.can_go(self._token):
            nav.go(self._token)
            self._consume()

        if nav.accept():
            return nav.data()

        self._error_expected(repr(t) for t in nav.edges())


def parse_selector(pref_string):
    return Parser().parse_selector(pref_string)


def main():
    pref_string = sys.argv[1]
    rules = parse_selector(pref_string)
    candidates = sys.argv[2:]
    print(repr(candidates))
    print(repr(rules.pick(candidates)))


if __name__ == "__main__":
    main()
