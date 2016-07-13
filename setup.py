#!/usr/bin/env python3


import dupescan

from setuptools import setup


setup(
    name             = "dupescan",
    version          = "0.0.2",
    description      = dupescan.__doc__.strip(),
    long_description = """TODO: LONG DESCRIPTION""",
    author           = "Jim Boswell",
    author_email     = "jimb@yellcorp.org",
    license          = "MIT",
    url              = "https://github.com/yellcorp/dupescan",

    packages=[ "dupescan" ],
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
            "correlate = dupescan.correlate:main",
            "finddupes = dupescan.finddupes:main"
        ]
    },
    # test_suite="tests"
)
