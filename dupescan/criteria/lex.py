from enum import Enum

from dupescan.criteria._common import ParseError


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
                return self._token(Token.Type.comma, None)

            if ch in "'\"":
                return self._quoted_string()

            return self._bare_string()
        return Token(Token.Type.end, None, "", self.pos)

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
        return self._token(Token.Type.string, "".join(value))

    def _quoted_string(self):
        value = [ ]
        quote = self.text[self.pos]
        assert quote in "'\""
        self.pos += 1
        while self.pos < self._len:
            ch = self.text[self.pos]
            self.pos += 1
            if ch == quote:
                return self._token(Token.Type.string, "".join(value))
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


class Token(object):
    class Type(Enum):
        string = 1
        comma = 2
        end = 3

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

    def is_type(self, token_type):
        return self.token_type == token_type

    def is_string(self, value=None):
        return self.token_type == Token.Type.string and (
            value is None or
            self.value == value
        )


ESCAPES = {
    "0": "\0",
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
