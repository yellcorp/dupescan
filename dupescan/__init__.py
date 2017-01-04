"""
Library and command-line utilities to detect duplicate files by content.
"""

__version__ = "0.0.9-develop"


from dupescan.algo import find_duplicate_files
from dupescan.fs import (
    FileEntry,
    flat_iterator,
    recurse_iterator,
    unique_entries,
)
