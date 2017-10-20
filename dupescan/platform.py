__all__ = (
    "DEFAULT_BUFFER_SIZE",
    "decide_max_open_files",
    "dev_and_inode",
)


MIN_BUFFER_SIZE = 4096
DEFAULT_MAX_BUFFER_SIZE = 1024 ** 2 # 1mb. on my machine this seems to be the sweet spot
DEFAULT_MAX_MEMORY = 256 * (1024 ** 2) # 256mb


ABSOLUTE_MAX_OPEN_FILES = 32768
FALLBACK_MAX_OPEN_FILES = 1024
def decide_max_open_files():
    try:
        import resource

        rid = None
        if hasattr(resource, "RLIMIT_NOFILE"):
            rid = resource.RLIMIT_NOFILE
        elif hasattr(resource, "RLIMIT_OFILE"):
            rid = resource.RLIMIT_OFILE

        if rid is not None:
            soft_limit, _ = resource.getrlimit(rid)
            if soft_limit == resource.RLIM_INFINITY:
                return ABSOLUTE_MAX_OPEN_FILES

            return max(1, int(soft_limit * 0.75))

    except ImportError:
        pass

    return FALLBACK_MAX_OPEN_FILES
