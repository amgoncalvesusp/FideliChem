"""Unit tests for multi-scoring agreement and correlation metrics."""

from __future__ import annotations

import pytest

from fidelichem.analytics.agreement import (
    compute_campaign_agreement,
    compute_kendall_tau,
    compute_molecule_agreement,
    compute_spearman_correlation,
)
from fidelichem.analytics.models import AgreementLevel


def test_correlations() -> None:
    x = [1.0, 2.0, 3.0, 4.0, 5.0]
    y_perf = [10.0, 20.0, 30.0, 40.0, 50.0]
    y_inv = [50.0, 40.0, 30.0, 20.0, 10.0]

    assert pytest.approx(compute_spearman_correlation(x, y_perf), rel=1e-3) == 1.0
    assert pytest.approx(compute_spearman_correlation(x, y_inv), rel=1e-3) == -1.0

    assert pytest.approx(compute_kendall_tau(x, y_perf), rel=1e-3) == 1.0
    assert pytest.approx(compute_kendall_tau(x, y_inv), rel=1e-3) == -1.0


def test_molecule_agreement() -> None:
    # High agreement: tight percentiles across 3 methods
    high_pcts = {"chemplp": 0.95, "goldscore": 0.93, "vina": 0.91}
    agr_high = compute_molecule_agreement(high_pcts, compound_id="CMPD_1")
    assert agr_high.agreement_level == AgreementLevel.HIGH
    assert agr_high.method_count == 3
    assert pytest.approx(agr_high.percentile_range, rel=1e-3) == 0.04

    # Low agreement: wide disagreement (0.95 vs 0.20)
    low_pcts = {"chemplp": 0.95, "goldscore": 0.20}
    agr_low = compute_molecule_agreement(low_pcts, compound_id="CMPD_2")
    assert agr_low.agreement_level == AgreementLevel.LOW
    assert pytest.approx(agr_low.percentile_range, rel=1e-3) == 0.75

    # Single method
    single_pcts = {"chemplp": 0.95, "goldscore": None}
    agr_single = compute_molecule_agreement(single_pcts, compound_id="CMPD_3")
    assert agr_single.agreement_level == AgreementLevel.UNKNOWN
    assert agr_single.method_count == 1


def test_campaign_agreement() -> None:
    score_table = {
        "C1": {"chemplp": 90.0, "goldscore": 80.0, "vina": -10.0},
        "C2": {"chemplp": 80.0, "goldscore": 70.0, "vina": -9.0},
        "C3": {"chemplp": 70.0, "goldscore": 60.0, "vina": -8.0},
        "C4": {"chemplp": 60.0, "goldscore": 50.0, "vina": -7.0},
        "C5": {"chemplp": 50.0, "goldscore": 40.0, "vina": -6.0},
    }

    camp = compute_campaign_agreement(score_table, top_k_fraction=0.4)
    assert set(camp.scoring_methods) == {"chemplp", "goldscore", "vina"}
    assert camp.spearman_matrix["chemplp"]["goldscore"] == 1.0
    assert "chemplp:goldscore" in camp.top_k_overlap
