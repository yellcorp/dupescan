"""
Library and command-line utilities to detect duplicate files by content.
"""

__version__ = "0.0.7"


import dupescan.correlate as correlate
import dupescan.criteria as criteria
import dupescan.finddupes as finddupes
import dupescan.report as report
import dupescan.units as units
import dupescan.walk as walk

from dupescan.algo import find_duplicate_files
