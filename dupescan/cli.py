from dupescan import (
    __version__,
    algo,
    units,
)


def add_common_cli_args(arg_parser):
    arg_parser.add_argument("--buffer-size",
        type=units.parse_byte_count,
        default=algo.DEFAULT_BUFFER_SIZE,
        metavar="SIZE",
        help="""Specifies the size of each buffer used when comparing files by
                content. This option accepts a byte count.  The default is
                %(default)s."""
    )

    arg_parser.add_argument("--version",
        action="version",
        version="%(prog)s " + __version__
    )
