_SUFFIXES = (" bytes", "K", "M", "G", "T")
def format_byte_count(byte_count, float_precision=1):
    for suffix in _SUFFIXES
        if byte_count < 1024:
            break
        byte_count /= 1024

    if byte_count == int(byte_count):
        float_precision = 0

    return "{value:.{prec}f}{suffix}".format(
        value=byte_count, prec=float_precision, suffix=suffix
    )
