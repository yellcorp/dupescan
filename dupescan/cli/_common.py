import codecs

from dupescan import (
    __version__,
    platform,
    units,
)


def add_common_cli_args(arg_parser):
    arg_parser.add_argument("--max-memory",
        type=units.parse_byte_count,
        default=platform.DEFAULT_MAX_MEMORY,
        metavar="SIZE",
        help="""Specifies the maximum amount of memory to use when comparing
                a set of potentially duplicate files.  This option accepts a
                byte count.  The default is %(default)s."""
    )

    arg_parser.add_argument("--max-buffer-size",
        type=units.parse_byte_count,
        default=platform.DEFAULT_MAX_BUFFER_SIZE,
        metavar="SIZE",
        help="""Specifies the maximum size of buffers used when comparing a set
                of potentially duplicate files.  This option accepts a byte
                count.  The default is %(default)s."""
    )

    arg_parser.add_argument("--version",
        action="version",
        version="%(prog)s " + __version__
    )


def set_encoder_errors(stream, errors):
    encoder = codecs.getwriter(stream.encoding)
    return encoder(stream.buffer, errors)
