"""
Library and command-line utilities to detect duplicate files by content.
"""

__version__ = "0.0.3"


import dupescan.correlate as correlate
import dupescan.criteria as criteria
import dupescan.finddupes as finddupes
import dupescan.report as report
import dupescan.unitformat as unitformat
import dupescan.walk as walk

from dupescan.algo import find_duplicate_files
