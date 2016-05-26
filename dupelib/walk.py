import os


def recurse_iterator(paths):
    for path in paths:
        if os.path.isdir(path):
            for container, dirs, files in os.walk(path):
                # modify dirs based on filter
                # exclude symlinks (?)
                # exclude 0-files
                for f in files:
                    yield os.path.join(container, f)
        else:
            yield path
