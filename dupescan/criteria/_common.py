class ParseError(Exception):
    def __init__(self, message, position=None, length=None):
        Exception.__init__(self, message, position, length)
        self.message = message
        self.position = position
        self.length = length

    @classmethod
    def from_token(cls, message, token):
        return cls(message, token.position, len(token.text))

    def __str__(self):
        buf = [ self.message ]
        if self.position is not None:
            buf.append(" at position {}".format(self.position))
            if self.length is not None and self.length > 1:
                buf.append("-{}".format(self.position + self.length - 1))
        return "".join(buf)
