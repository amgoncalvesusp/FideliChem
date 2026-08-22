"""Direction-aware normalization engine and statistical distribution summaries."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

from fidelichem.domain.scoring import (
    NormalizedScoreObservation,
    ScoreDefinition,
    ScoreDirection,
    ScoreDistributionStats,
)


def _compute_median(sorted_vals: list[float]) -> float:
    """Compute the median of an already sorted list of floats."""
    n = len(sorted_vals)
    if n == 0:
        return 0.0
    mid = n // 2
    if n % 2 == 1:
        return sorted_vals[mid]
    return (sorted_vals[mid - 1] + sorted_vals[mid]) / 2.0


def _compute_percentile(sorted_vals: list[float], p: float) -> float:
    """Compute empirical percentile value (0.0 to 1.0) on sorted floats."""
    n = len(sorted_vals)
    if n == 0:
        return 0.0
    if n == 1:
        return sorted_vals[0]
    idx = p * (n - 1)
    low = int(math.floor(idx))
    high = int(math.ceil(idx))
    weight = idx - low
    return (1.0 - weight) * sorted_vals[low] + weight * sorted_vals[high]


class ScoreNormalizer:
    """Engine computing relative percentiles, ranks, and robust Z-scores."""

    def normalize_values(
        self,
        records: Sequence[dict[str, Any]],
        *,
        definition: ScoreDefinition,
        scope_key: str,
        value_key: str = "raw_value",
        entity_key: str = "entity_reference",
    ) -> tuple[tuple[NormalizedScoreObservation, ...], ScoreDistributionStats]:
        """Normalize scores within a comparability scope preserving missingness."""
        total_count = len(records)
        observed_entries: list[tuple[float, str | None, dict[str, Any]]] = []
        missing_count = 0

        for r in records:
            raw = r.get(value_key)
            entity = r.get(entity_key)
            if raw is None:
                missing_count += 1
                continue
            try:
                num = float(raw)
                if math.isfinite(num):
                    observed_entries.append((num, entity, r))
                else:
                    missing_count += 1
            except (ValueError, TypeError):
                missing_count += 1

        observed_count = len(observed_entries)
        if observed_count == 0:
            empty_stats = ScoreDistributionStats(
                score_key=definition.key,
                scope_key=scope_key,
                count_total=total_count,
                count_observed=0,
                count_missing=missing_count,
            )
            return ((), empty_stats)

        # Sort raw values for distribution statistics
        sorted_raws = sorted(item[0] for item in observed_entries)
        min_raw = sorted_raws[0]
        max_raw = sorted_raws[-1]
        median_raw = _compute_median(sorted_raws)
        q25_raw = _compute_percentile(sorted_raws, 0.25)
        q75_raw = _compute_percentile(sorted_raws, 0.75)
        iqr_raw = q75_raw - q25_raw
        mean_raw = sum(sorted_raws) / observed_count

        variance = (
            sum((x - mean_raw) ** 2 for x in sorted_raws) / observed_count
            if observed_count > 0
            else 0.0
        )
        std_raw = math.sqrt(variance)

        # Median Absolute Deviation (MAD) for robust Z
        sorted_abs_devs = sorted(abs(x - median_raw) for x in sorted_raws)
        mad = _compute_median(sorted_abs_devs)

        # Sort entries according to direction (best first)
        is_higher_better = definition.direction == ScoreDirection.HIGHER_BETTER
        ranked_entries = sorted(
            observed_entries,
            key=lambda x: -x[0] if is_higher_better else x[0],
        )

        normalized_obs: list[NormalizedScoreObservation] = []
        n = observed_count

        # Assign ranks and percentiles handling ties
        for idx, (raw_val, entity, _orig_record) in enumerate(ranked_entries):
            # Check if this item ties with previous
            if idx > 0 and raw_val == ranked_entries[idx - 1][0]:
                # Tie: retain previous rank
                rank = normalized_obs[-1].rank
                percentile = normalized_obs[-1].percentile
            else:
                rank = idx + 1
                percentile = 1.0 if n <= 1 else (n - rank) / (n - 1)

            # Robust Z-score (oriented so that better candidate has higher Z)
            if mad > 1e-9:
                if is_higher_better:
                    robust_z = (raw_val - median_raw) / (1.4826 * mad)
                else:
                    robust_z = (median_raw - raw_val) / (1.4826 * mad)
            else:
                robust_z = 0.0

            # Standard Z-score (oriented so that better candidate has higher Z)
            if std_raw > 1e-9:
                if is_higher_better:
                    standard_z = (raw_val - mean_raw) / std_raw
                else:
                    standard_z = (mean_raw - raw_val) / std_raw
            else:
                standard_z = 0.0

            normalized_obs.append(
                NormalizedScoreObservation(
                    score_key=definition.key,
                    raw_value=raw_val,
                    direction=definition.direction,
                    scope_key=scope_key,
                    rank=rank,
                    percentile=percentile,
                    robust_z=robust_z,
                    standard_z=standard_z,
                    entity_reference=str(entity) if entity is not None else None,
                )
            )

        stats = ScoreDistributionStats(
            score_key=definition.key,
            scope_key=scope_key,
            count_total=total_count,
            count_observed=observed_count,
            count_missing=missing_count,
            min_raw=min_raw,
            max_raw=max_raw,
            median_raw=median_raw,
            q25_raw=q25_raw,
            q75_raw=q75_raw,
            iqr_raw=iqr_raw,
            mean_raw=mean_raw,
            std_raw=std_raw,
        )

        return (tuple(normalized_obs), stats)


__all__ = ["ScoreNormalizer"]
