"""Statistical agreement, rank correlation, and top-k consistency metrics."""

from __future__ import annotations

import math
import statistics
from collections.abc import Mapping, Sequence

from .models import AgreementLevel, CampaignAgreement, MoleculeAgreement


def _rank_vector(values: Sequence[float]) -> list[float]:
    """Compute fractional midranks for values handling ties."""
    indexed = sorted(enumerate(values), key=lambda x: x[1])
    ranks = [0.0] * len(values)
    i = 0
    n = len(values)
    while i < n:
        j = i
        while j < n - 1 and indexed[j + 1][1] == indexed[j][1]:
            j += 1
        avg_rank = (i + 1 + j + 1) / 2.0
        for k in range(i, j + 1):
            ranks[indexed[k][0]] = avg_rank
        i = j + 1
    return ranks


def compute_spearman_correlation(
    x: Sequence[float], y: Sequence[float]
) -> float | None:
    """Compute Spearman rank correlation coefficient between paired sequences."""
    if len(x) != len(y) or len(x) < 2:
        return None

    finite_pairs = [
        (a, b)
        for a, b in zip(x, y, strict=True)
        if math.isfinite(a) and math.isfinite(b)
    ]
    if len(finite_pairs) < 2:
        return None

    x_clean = [p[0] for p in finite_pairs]
    y_clean = [p[1] for p in finite_pairs]

    rx = _rank_vector(x_clean)
    ry = _rank_vector(y_clean)

    mean_rx = statistics.mean(rx)
    mean_ry = statistics.mean(ry)

    num = sum((a - mean_rx) * (b - mean_ry) for a, b in zip(rx, ry, strict=True))
    den_x = sum((a - mean_rx) ** 2 for a in rx)
    den_y = sum((b - mean_ry) ** 2 for b in ry)

    den = math.sqrt(den_x * den_y)
    if den == 0.0:
        return None
    corr = num / den
    return max(-1.0, min(1.0, corr))


def compute_kendall_tau(x: Sequence[float], y: Sequence[float]) -> float | None:
    """Compute Kendall's tau rank correlation coefficient."""
    if len(x) != len(y) or len(x) < 2:
        return None

    finite_pairs = [
        (a, b)
        for a, b in zip(x, y, strict=True)
        if math.isfinite(a) and math.isfinite(b)
    ]
    n = len(finite_pairs)
    if n < 2:
        return None

    concordant = 0
    discordant = 0
    for i in range(n):
        for j in range(i + 1, n):
            xi, yi = finite_pairs[i]
            xj, yj = finite_pairs[j]
            dx = xi - xj
            dy = yi - yj
            prod = dx * dy
            if prod > 0:
                concordant += 1
            elif prod < 0:
                discordant += 1

    total_pairs = n * (n - 1) / 2.0
    if total_pairs == 0:
        return None
    tau = (concordant - discordant) / total_pairs
    return max(-1.0, min(1.0, tau))


def compute_molecule_agreement(
    percentiles: Mapping[str, float | None],
    compound_id: str,
    high_threshold: float = 0.15,
    mod_threshold: float = 0.35,
) -> MoleculeAgreement:
    """Classify score consistency for a single molecule across scoring functions."""
    valid_pcts = [v for v in percentiles.values() if v is not None and math.isfinite(v)]
    method_count = len(valid_pcts)

    if method_count < 2:
        return MoleculeAgreement(
            compound_id=compound_id,
            percentile_range=None,
            percentile_std=None,
            agreement_level=AgreementLevel.UNKNOWN,
            method_count=method_count,
        )

    pct_range = max(valid_pcts) - min(valid_pcts)
    pct_std = statistics.stdev(valid_pcts)

    if pct_range <= high_threshold:
        level = AgreementLevel.HIGH
    elif pct_range <= mod_threshold:
        level = AgreementLevel.MODERATE
    else:
        level = AgreementLevel.LOW

    return MoleculeAgreement(
        compound_id=compound_id,
        percentile_range=pct_range,
        percentile_std=pct_std,
        agreement_level=level,
        method_count=method_count,
    )


def compute_campaign_agreement(
    score_table: Mapping[str, Mapping[str, float | None]],
    top_k_fraction: float = 0.1,
) -> CampaignAgreement:
    """Compute global agreement matrix and top-k overlap across campaign scores."""
    methods_set: set[str] = set()
    for row in score_table.values():
        methods_set.update(row.keys())
    methods = tuple(sorted(methods_set))

    spearman_mat: dict[str, dict[str, float | None]] = {m: {} for m in methods}
    kendall_mat: dict[str, dict[str, float | None]] = {m: {} for m in methods}
    top_k_overlap: dict[str, float] = {}
    pair_counts: dict[str, int] = {}

    for i, m1 in enumerate(methods):
        spearman_mat[m1][m1] = 1.0
        kendall_mat[m1][m1] = 1.0
        for j in range(i + 1, len(methods)):
            m2 = methods[j]
            paired_ids: list[str] = []
            x_vals: list[float] = []
            y_vals: list[float] = []

            for cmpd_id, row in score_table.items():
                v1 = row.get(m1)
                v2 = row.get(m2)
                if (
                    v1 is not None
                    and v2 is not None
                    and math.isfinite(v1)
                    and math.isfinite(v2)
                ):
                    paired_ids.append(cmpd_id)
                    x_vals.append(v1)
                    y_vals.append(v2)

            key = f"{m1}:{m2}"
            pair_counts[key] = len(paired_ids)

            sp = compute_spearman_correlation(x_vals, y_vals)
            kd = compute_kendall_tau(x_vals, y_vals)
            spearman_mat[m1][m2] = sp
            spearman_mat[m2][m1] = sp
            kendall_mat[m1][m2] = kd
            kendall_mat[m2][m1] = kd

            # Top-k Jaccard overlap
            if len(paired_ids) >= 2:
                k_count = max(1, int(math.ceil(len(paired_ids) * top_k_fraction)))
                sorted_m1 = sorted(
                    paired_ids,
                    key=lambda cid: score_table[cid][m1] or -math.inf,
                    reverse=True,
                )[:k_count]
                sorted_m2 = sorted(
                    paired_ids,
                    key=lambda cid: score_table[cid][m2] or -math.inf,
                    reverse=True,
                )[:k_count]
                set_m1 = set(sorted_m1)
                set_m2 = set(sorted_m2)
                union = set_m1 | set_m2
                jaccard = (len(set_m1 & set_m2) / len(union)) if union else 0.0
                top_k_overlap[key] = jaccard

    return CampaignAgreement(
        scoring_methods=methods,
        spearman_matrix=spearman_mat,
        kendall_matrix=kendall_mat,
        top_k_overlap=top_k_overlap,
        pair_counts=pair_counts,
    )


__all__ = [
    "compute_campaign_agreement",
    "compute_kendall_tau",
    "compute_molecule_agreement",
    "compute_spearman_correlation",
]
