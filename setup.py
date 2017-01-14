#!/usr/bin/env python3


import dupescan

from setuptools import setup
import os
import sys


with open(os.path.join(
        os.path.dirname(sys.modules["__main__"].__file__),
        "readme.rst"
    ), "r") as readme_stream:
    readme_text = readme_stream.read()


setup(
    name             = "dupescan",
    version          = dupescan.__version__,
    description      = dupescan.__doc__.strip(),
    long_description = readme_text,
    author           = "Jim Boswell",
    author_email     = "jimb@yellcorp.org",
    license          = "MIT",
    url              = "https://github.com/yellcorp/dupescan",

    packages=[
        "dupescan",
        "dupescan.cli",
        "dupescan.criteria",
    ],
    classifiers=[
        'Environment :: Console',
        'Intended Audience :: Developers',
        'Intended Audience :: End Users/Desktop',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3 :: Only',
        'Operating System :: POSIX :: Linux',
        'Operating System :: MacOS :: MacOS X',
        'Topic :: Utilities'
    ],
    entry_points={
        "console_scripts": [
            "correlate = dupescan.cli.correlate:main",
            "finddupes = dupescan.cli.finddupes:main"
        ]
    },
    # test_suite="tests"
)
