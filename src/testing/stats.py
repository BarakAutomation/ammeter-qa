"""
Statistical analysis of a completed run.

Uses only the Python standard library (statistics module) - see
DESIGN_DECISIONS.md for why numpy/scipy/pandas were deliberately not used.

Convention: the sample standard deviation needs at least two values, so it
is reported as None (null) when a run has a single successful measurement -
never as a made-up zero.
"""
import statistics
from typing import Dict, List, Optional


def compute_statistics(values: List[float]) -> Dict[str, Optional[float]]:
    if not values:
        raise ValueError("no successful measurements to analyse")
    return {
        "count": len(values),
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "stdev": statistics.stdev(values) if len(values) > 1 else None,
        "min": min(values),
        "max": max(values),
    }
