import functools
import sys


__all__ = (
    "select_level",
    "format_brace",
    "NullLogger", "StreamLogger",
    "CRITICAL", "ERROR", "WARNING", "INFO", "VERBOSE", "DEBUG", "MINIMUM",
)


CRITICAL = 50
ERROR = 40
WARNING = 30
INFO = 20
VERBOSE = 15
DEBUG = 10
MINIMUM = 0


def select_level(choices, zero_level, index):
    zero_index = choices.index(zero_level)
    index = max(0, min(len(choices) - 1, zero_index + index))
    return choices[index]


def format_brace(message, args, kwargs):
    if not args and not kwargs:
        return message
    return message.format(*args, **kwargs)


def log_method(level):
    def method(self, template, *targs, **tkwargs):
        self.log(level, template, *targs, **tkwargs)
    return method

class Logger(object):
    def __init__(self, format_func=None):
        self._format_func = format_func or str.format

    def _format(self, message, args, kwargs):
        if not args and not kwargs:
            return message
        return self._format_func(message, *args, **kwargs)

    def level_func(self, level):
        return functools.partial(self.log, level)

    def log(self, level, message, *message_args, **message_kwargs):
        raise NotImplementedError()

    critical = log_method(CRITICAL)
    error = log_method(ERROR)
    warning = log_method(WARNING)
    info = log_method(INFO)
    debug = log_method(DEBUG)


class NullLogger(Logger):
    def log(self, level, template, *targs, **tkwargs):
        pass


class StreamLogger(Logger):
    def __init__(self, format_func=None, stream=None, min_level=MINIMUM, max_level=None):
        super().__init__(format_func)
        self._stream = stream or sys.stdout
        self.min_level = min_level
        self.max_level = max_level

    def log(self, level, template, *targs, **tkwargs):
        if level >= self.min_level and (self.max_level is None or level < self.max_level):
            print(
                self._format(template, targs, tkwargs),
                file = self._stream
            )
