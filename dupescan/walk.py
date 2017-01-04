import os


def const_true(*args):
    return True


def recurse_iterator(paths, dir_path_filter=None, file_path_filter=None):
    if dir_path_filter is None:
        dir_path_filter = const_true

    if file_path_filter is None:
        file_path_filter = const_true

    for path in paths:
        if os.path.isdir(path):
            for container, dirs, files in os.walk(path):
                dirs[:] = [
                    d for d in dirs
                    if dir_path_filter(os.path.join(container, d))
                ]
                for f in files:
                    file_path = os.path.join(container, f)
                    if file_path_filter(file_path):
                        yield file_path
        elif file_path_filter(path):
            yield path


def no_repeated_paths(path_iterator):
    seen = set()
    for p in path_iterator:
        if p not in seen:
            seen.add(p)
            yield p
