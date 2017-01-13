from dupescan.criteria import (
    evaluate,
    lex,
)
from dupescan.criteria._common import ParseError


PROPERTY_GRAPH = None
OPERATOR_GRAPH = None
ADJECTIVE_GRAPH = None
MODIFIER_GRAPH = None

def lazy_init_module():
    global PROPERTY_GRAPH, OPERATOR_GRAPH, ADJECTIVE_GRAPH, MODIFIER_GRAPH
    if PROPERTY_GRAPH is not None:
        return

    PROPERTY_GRAPH = TokenGraph()
    evaluate.build_property_graph(PROPERTY_GRAPH)

    OPERATOR_GRAPH = TokenGraph()
    evaluate.build_operator_graph(OPERATOR_GRAPH)

    ADJECTIVE_GRAPH = TokenGraph()
    evaluate.build_adjective_graph(ADJECTIVE_GRAPH)

    MODIFIER_GRAPH = TokenGraph()
    evaluate.build_modifier_graph(MODIFIER_GRAPH)


class Parser(object):
    def __init__(self):
        lazy_init_module()
        self._lex = lex.Lexer()
        self._token = None

    def _error_expected(self, expected_tokens):
        expected_tokens = list(expected_tokens)
        if len(expected_tokens) == 1:
            expected_desc = expected_tokens[0]
        else:
            expected_desc = "one of {}".format(", ".join(expected_tokens))

        raise ParseError.from_token(
            "Expected {}".format(expected_desc),
            self._token
        )

    def _consume(self):
        self._token = self._lex.next_token()

    def parse_selector(self, text):
        self._lex.start(text)
        self._consume()

        criteria = self._criteria()
        return evaluate.SelectionRules(criteria)

    def _criteria(self):
        criteria = [ ]
        while True:
            criteria.append(self._criterion())

            if self._token.is_type(lex.Token.Type.end):
                return criteria
            elif self._token.is_type(lex.Token.Type.comma):
                self._consume()
            else:
                self._error_expected(("','", "end"))

    def _criterion(self):
        prop_nav = PROPERTY_GRAPH.navigator()
        adj_nav = ADJECTIVE_GRAPH.navigator()

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
        return self._parse_using(PROPERTY_GRAPH)

    def _operator(self):
        return self._parse_using(OPERATOR_GRAPH)

    def _adjective(self):
        return self._parse_using(ADJECTIVE_GRAPH)

    def _modifier(self):
        if MODIFIER_GRAPH.navigator().can_go(self._token):
            return self._parse_using(MODIFIER_GRAPH)
        return evaluate.CaseSensitiveContext()

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
                raise ParseError.from_token("Unexpected token", token)

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
