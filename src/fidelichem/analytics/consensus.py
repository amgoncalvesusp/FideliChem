"""Score consensus engine aggregating multi-fidelity scoring percentiles."""

from __future__ import annotations

import math
import statistics
from collections.abc import Mapping

from .models import ScoreConsensusResult


def compute_score_consensus(
    compound_percentiles: Mapping[str, Mapping[str, float | None]],
    compound_ranks: Mapping[str, Mapping[str, int | None]] | None = None,
    compound_raw_scores: Mapping[str, Mapping[str, float | None]] | None = None,
    weights: Mapping[str, float] | None = None,
) -> list[ScoreConsensusResult]:
    """Calculate consensus statistics across scoring methods for each candidate.

    Missing data is never silently converted to zero.
    """
    results: list[ScoreConsensusResult] = []
    compound_ranks = compound_ranks or {}
    compound_raw_scores = compound_raw_scores or {}
    weights = weights or {}

    for cmpd_id, method_pcts in compound_percentiles.items():
        valid_items = [
            (method, val)
            for method, val in method_pcts.items()
            if val is not None and math.isfinite(val)
        ]
        method_count = len(valid_items)

        if not valid_items:
            results.append(
                ScoreConsensusResult(
                    compound_id=cmpd_id,
                    median_percentile=None,
                    mean_percentile=None,
                    weighted_percentile=None,
                    rank_dispersion=None,
                    method_count=0,
                    raw_scores=dict(compound_raw_scores.get(cmpd_id, {})),
                    percentiles=dict(method_pcts),
                    ranks=dict(compound_ranks.get(cmpd_id, {})),
                )
            )
            continue

        pct_values = [v for _, v in valid_items]
        med_val = statistics.median(pct_values)
        mean_val = statistics.mean(pct_values)
        dispersion = statistics.stdev(pct_values) if len(pct_values) > 1 else 0.0

        total_weight = 0.0
        weighted_sum = 0.0
        for method, val in valid_items:
            w = weights.get(method, 1.0)
            if w > 0:
                weighted_sum += w * val
                total_weight += w

        weighted_val = (weighted_sum / total_weight) if total_weight > 0 else mean_val

        results.append(
            ScoreConsensusResult(
                compound_id=cmpd_id,
                median_percentile=med_val,
                mean_percentile=mean_val,
                weighted_percentile=weighted_val,
                rank_dispersion=dispersion,
                method_count=method_count,
                raw_scores=dict(compound_raw_scores.get(cmpd_id, {})),
                percentiles=dict(method_pcts),
                ranks=dict(compound_ranks.get(cmpd_id, {})),
            )
        )

    # Sort descending by median percentile (best candidates first)
    results.sort(
        key=lambda r: (
            r.median_percentile is None,
            -(r.median_percentile or 0.0),
        )
    )
    return results


__all__ = ["compute_score_consensus"]
