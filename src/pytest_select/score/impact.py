"""Impact scoring: breadth of code exercised by a test."""

from __future__ import annotations


def compute_impact_percentiles(raw_counts: dict[str, float]) -> dict[str, float]:
    """
    Map raw reach counts to 0-100 percentile rank across suite.
    Higher impact = exercises more files.
    """
    if not raw_counts:
        return {}
    values = sorted(raw_counts.items(), key=lambda x: x[1])
    n = len(values)
    if n == 1:
        return {values[0][0]: 50.0}
    result: dict[str, float] = {}
    for rank, (nodeid, _) in enumerate(values):
        # percentile: fraction of tests with strictly lower impact
        pct = 100.0 * rank / (n - 1) if n > 1 else 50.0
        result[nodeid] = pct
    return result
