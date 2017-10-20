__all__ = (
    "StatusLine",
)


def prepare_text(text, max_len, elide_string, elide_point):
    stext, _, _ = str(text).partition("\n")
    stext = stext.replace("\t", "    ")
    
    if len(stext) > max_len:
        lead_len = int(0.5 + elide_point * max_len - len(elide_string))
        return "%s%s%s" % (
            stext[:lead_len],
            elide_string,
            stext[-max_len + lead_len + len(elide_string):]
        )
    
    return stext


class StatusLine(object):
    def __init__(self, stream, line_width=78, elide_string="...", elide_point=0.33):
        self._stream = stream
        self._line_width = line_width
        self._last_len = 0
        self._elide_string = str(elide_string)
        self._elide_point = elide_point

    @property
    def line_width(self):
        return self._line_width

    def clear(self):
        self.set_text("")
        self.set_text("")

    def set_text(self, new_text):
        text = prepare_text(new_text, self._line_width, self._elide_string, self._elide_point)
        now_len = len(text)

        self._stream.write("\r%s" % text)
        if now_len < self._last_len:
            self._stream.write(" " * (self._last_len - now_len))
        self._stream.flush()
        self._last_len = now_len
