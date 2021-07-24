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


usage: finddupes [-h] [-s] [-z] [-o] [-m SIZE] [-p CRITERIA] [--exclude NAME]
                 [--time] [--help-prefer] [-v] [--no-progress] [-x PATH]
                 [-c PATH] [-n] [--max-memory SIZE] [--max-buffer-size SIZE]
                 [--version]
                 [PATH ...]

Find files with identical content.

positional arguments:
  PATH                  List of files to consider. Directories will be
                        recursively examined.

optional arguments:
  -h, --help            show this help message and exit
  -s, --symlinks        Include symlinks.
  -z, --zero            Include zero-length files. All zero-length files are
                        considered to have identical content. This option is
                        equivalent to --min-size 0
  -o, --only-mixed-roots
                        Only show duplicate files if they arise from recursing
                        into different root directories. This can speed
                        operations if the only results of interest are whether
                        duplicates exist between different filesystem
                        hierarchies, rather than within a single one. Note
                        that this only has a useful effect if two or more
                        paths are provided.
  -m SIZE, --min-size SIZE
                        Ignore files smaller than SIZE. This option accepts a
                        byte count. The default is 1.
  -p CRITERIA, --prefer CRITERIA
                        For each set of duplicate files, automatically select
                        one for preservation according to the provided
                        criteria. Other duplicates can be deleted by passing
                        the generated report to the -x/--delete option.
  --exclude NAME        Excludes files or directories with the given name.
                        This feature is is currently simplified - it only
                        performs case-sensitive literal comparisons against a
                        filename - i.e. the last segment of the file path. At
                        some point it will be expanded to something more like
                        rsync/tar matching.
  --time                Add elasped time to the generated report.
  --help-prefer         Display detailed help on using the --prefer option
  -v, --verbose         Log detailed information to STDERR.
  --no-progress         Don't show progress bars on STDERR.
  -x PATH, --delete PATH
                        Delete unmarked files in the report at PATH. Sets
                        where no files are marked will be skipped.
  -c PATH, --coalesce PATH
                        Replace duplicate files with hard links, using sets
                        found in the report at PATH. File marks are ignored -
                        all filenames are preserved.
  -n, --dry-run         Used in combination with -x/--delete or -c/--coalesce.
                        List actions that those options would perform without
                        actually doing them.
  --max-memory SIZE     Specifies the maximum amount of memory to use when
                        comparing a set of potentially duplicate files. This
                        option accepts a byte count. The default is 268435456.
  --max-buffer-size SIZE
                        Specifies the maximum size of buffers used when
                        comparing a set of potentially duplicate files. This
                        option accepts a byte count. The default is 1048576.
  --version             show program's version number and exit

Arguments that accept byte counts accept an integer with an optional suffix
indicating units. 'B' indicates bytes, which is also the default if no suffix
is provided. 'K' indicates kibibytes (1024 bytes). 'M' indicates mebibytes.
'G' indicates gibibytes, and 'T' indicates tebibytes.

Automatically marking duplicates with --prefer
''''''''''''''''''''''''''''''''''''''''''''''

When finddupes is run with the --prefer option, it will examine each set of
duplicate files discovered, and attempt to mark one of them as 'preferred',
according to a set of criteria provided by the user.

Example:

    $ finddupes -r . --prefer "shorter path"
    ## Size: 100K Instances: 3 Excess: 200K Names: 3
      ./Copy of photo.jpg
      ./backup/photo.jpg
    > ./photo.jpg

In this case 'photo.jpg' is the preferred copy because it has the shortest
path.

This report can then be used to delete the non-preferred duplicates by saving
the report to a file and rerunning finddupes with the --delete option.

A criteria string is a phrase, or a series of phrases, expressing what
properties of a file should make it the preferred one among a set of
duplicates.  For each set of duplicates, the selection process begins with all
files marked.  Each phrase, starting with the first, is tested against the
marked files, and those that do not pass are unmarked.  Phrases are considered
until only one file is marked, or there are no more phrases.

If the selection process ends with a single file, it is indicated in the report
with a '>' symbol. If there remains more than one file marked, they are
indicated with '?'.

Example:

    $ finddupes -r . --prefer "shorter path"
    ## Size: 100K Instances: 4 Excess: 300K Names: 4
      ./Copy of photo2.jpg
      ./backup/photo1.jpg
    ? ./photo1.jpg
    ? ./photo2.jpg

In this case, both 'photo1.jpg' and 'photo2.jpg' are marked because there is no
single shortest path, and there are no other criteria to prefer one of these
over the other. This could be resolved with a second criteria, for example:

    $ finddupes -r . --prefer "shorter path, earlier path"
    ## Size: 100K Instances: 4 Excess: 300K Names: 4
      ./Copy of photo2.jpg
      ./backup/photo1.jpg
    > ./photo1.jpg
      ./photo2.jpg

In this sense, 'earlier' means lexicographically earlier, or lesser - a name
that appears earlier in a list when sorted.  Now 'photo1.jpg' wins over
'photo2.jpg'.  Note that 'Copy of photo2.jpg' is not considered, even though it
sorts earliest of all, because it was eliminated by the first 'shorter path'
criterion.

Criteria strings make use of spaces, so the entire set of criteria phrases must
be escaped appropriately for your shell. Generally this means surrounding them
with single or double quotes.

A criteria string must be a single argument that follows the --prefer option,
and has the following grammar.

CRITERIA : PHRASE ( , PHRASE ) *
  A CRITERIA is a one or more PHRASEs, separated by commas (,).

PHRASE : BOOLEAN_PHRASE | EXTREMA_PHRASE
  A PHRASE is a BOOLEAN_PHRASE or a EXTREMA_PHRASE.

BOOLEAN_PHRASE : PROPERTY OPERATOR ARGUMENT [ MODIFIER ]
  Such phrases prefer files that pass some kind of a true/false test.

EXTREMA_PHRASE : ADJECTIVE PROPERTY [ MODIFIER ]
  Such phrases prefer files that occur first or last when sorted by some
  property.

PROPERTY  : path
            The file's full path, relative to the working directory.

          | name
            The file's name - that is, the path from just after the last
            directory separator to the end.

          | directory
            The file's containing directory - that is, the path up until the
            last directory separator.

          | directory name
            The name of the file's containing directory - that is, the path
            between the second-last path separator and the last one.

          | extension
            The file's extension, including the '.' if present.  If the file
            lacks an extension, it is considered to be "" - the empty string.

          | mtime
          | modification time
            The file's modification time.

          | index
            The position of the file, or its ancestor directory, on the
            command line. The first file/directory has an index of 1.

OPERATOR  : is
            Prefer strings/numbers that are equal to the argument.

          | is not
            Prefer strings/numbers that are not equal to the argument.

          | contains
            Prefer strings that contain the argument.

          | not contains
            Prefer strings that do not contain the argument.

          | starts with
            Prefer strings in which the argument occurs at the start.

          | not starts with
            Prefer strings in which the argument does not occur at the start.

          | ends with
            Prefer strings in which the argument occurs at the end.

          | not ends with
            Prefer strings in which the argument does not occur at the end.

          | matches re
          | matches regex
          | matches regexp
            Interpret the argument as a regular expression, and prefer strings
            that match it.

          | not matches re
          | not matches regex
          | not matches regexp
            Prefer strings that do not match the argument.

ADJECTIVE : shorter
            Prefer shorter strings.

          | longer
            Prefer longer strings.

          | shallower
            Prefer strings containing fewer directory separators.

          | deeper
            Prefer strings containing more directory separators.

          | earlier
          | lower
            When used with strings: prefer ones that appear earlier when sorted.
            When used with times: prefer earlier ones.
            When used with numbers: prefer lower ones.

          | later
          | higher
            When used with strings: prefer ones that appear later when sorted.
            When used with times: prefer later ones.
            When used with numbers: prefer higher ones.

ARGUMENT  : BARE_STRING
            A sequence of characters terminated by the first unescaped space.
            Spaces and backslashes can be included by prepending them with a
            backslash (\\).

          | SINGLE_QUOTED_STRING
            A sequence of characters surrounded by single quotes ('). Single
            quotes and backslashes can be included by prepending them with a
            backslash (\\).

          | DOUBLE_QUOTED_STRING
            A sequence of characters surrounded by double quotes ("). Double
            quotes and backslashes can be included by prepending them with a
            backslash (\\).

MODIFIER  : ignoring case
  This will cause all string comparisons and tests to ignore letter case.


correlate
~~~~~~~~~

usage: correlate [-h] [-v] [-m] [-r] [-a] [-c] [--no-colorize] [--no-summary]
                 [--max-memory SIZE] [--max-buffer-size SIZE] [--version]
                 DIR DIR

Compare two directories by content.

positional arguments:
  DIR                   Paths to the directories to be compared.

optional arguments:
  -h, --help            show this help message and exit
  -v, --verbose         Log detailed information to STDERR.
  -m, --matches         List files that appear in both directories.
  -r, --removes         List files that appear only as a descendant of the
                        first directory.
  -a, --adds            List files that appear only as a descendant of the
                        second directory.
  -c, --colorize        Colorize output.
  --no-colorize         Force colorizing off. If neither --colorize or --no-
                        colorize is specified, it will be enabled if a
                        compatible terminal is detected.
  --no-summary          Suppress the summary.
  --max-memory SIZE     Specifies the maximum amount of memory to use when
                        comparing a set of potentially duplicate files. This
                        option accepts a byte count. The default is 268435456.
  --max-buffer-size SIZE
                        Specifies the maximum size of buffers used when
                        comparing a set of potentially duplicate files. This
                        option accepts a byte count. The default is 1048576.
  --version             show program's version number and exit

If none of -m/--matches, -r/--removes, -a/--adds is specified, all are
reported.
