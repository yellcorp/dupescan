dupescan
========

Python 3 library and CLI utilities for finding files with identical content.

Copyright (c) 2016 Jim Boswell.  Licensed under the Expat MIT license.  See the
file LICENSE for the full text.

TODO
----

Some semblance of proper documentation

CLI Usage
---------

finddupes
~~~~~~~~~

usage: finddupes [-h] [-s] [-z] [-a] [-r] [-p CRITERIA] [--help-prefer] [-v]
                 [-x PATH] [-n] [--version]
                 [PATH [PATH ...]]

Find files with identical content.

positional arguments:
  PATH                  List of files to consider. Specify --recurse (-r) to
                        also consider the contents of directories.

optional arguments:
  -h, --help            show this help message and exit
  -s, --symlinks        Include symlinks.
  -z, --zero            Include zero-length files. All zero-length files are
                        considered to have identical content.
  -a, --aliases         Check whether a single file has more than one name,
                        which is possible through hardlinks, as well as
                        symlinks if the -s/--symlinks option is specified.
                        This check is used to skip redundant content
                        comparisons, add extra information to reports, and
                        preserve all paths pointing to a selected file when
                        the -p/--prefer option is used.
  -r, --recurse         Recurse into subdirectories.
  -p CRITERIA, --prefer CRITERIA
                        For each set of duplicate files, automatically select
                        one for preservation according to the provided
                        criteria. Other duplicates can be deleted by passing
                        the generated report to the -x/--execute option.
  --help-prefer         Display detailed help on using the --prefer option
  -v, --verbose         Log detailed information to STDERR.
  -x PATH, --execute PATH
                        Delete unmarked files in the report at PATH. Sets
                        where no files are marked will be skipped.
  -n, --dry-run         Used in combination with -x/--execute. List actions
                        that --execute would perform without actually doing
                        them.
  --version             show program's version number and exit

correlate
~~~~~~~~~

usage: correlate [-h] [-v] [-m] [-r] [-a] [-c] [--no-colorize] [--no-summary]
                 [--version]
                 DIR DIR

Compare two directories by content.

positional arguments:
  DIR             Paths to the directories to be compared.

optional arguments:
  -h, --help      show this help message and exit
  -v, --verbose   Log detailed information to STDERR.
  -m, --matches   List files that appear in both directories.
  -r, --removes   List files that appear only as a descendant of the first
                  directory.
  -a, --adds      List files that appear only as a descendant of the second
                  directory.
  -c, --colorize  Colorize output.
  --no-colorize   Force colorizing off. If neither --colorize or --no-colorize
                  is specified, it will be enabled if a compatible terminal is
                  detected.
  --no-summary    Suppress the summary.
  --version       show program's version number and exit

If none of -m/--matches, -r/--removes, -a/--adds is specified, all are
reported.
