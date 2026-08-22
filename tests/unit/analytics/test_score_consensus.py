"""Unit tests for multi-method score consensus calculation."""

from __future__ import annotations

import pytest

from fidelichem.analytics.consensus import compute_score_consensus


def test_score_consensus_full_data() -> None:
    percentiles = {
        "CMPD_A": {"chemplp": 0.95, "goldscore": 0.90, "vina": 0.85},
        "CMPD_B": {"chemplp": 0.40, "goldscore": 0.50, "vina": 0.60},
    }
    raw_scores = {
        "CMPD_A": {"chemplp": 85.0, "goldscore": 75.0, "vina": -9.2},
        "CMPD_B": {"chemplp": 45.0, "goldscore": 40.0, "vina": -6.5},
    }

    results = compute_score_consensus(
        compound_percentiles=percentiles,
        compound_raw_scores=raw_scores,
    )
    assert len(results) == 2

    res_a = next(r for r in results if r.compound_id == "CMPD_A")
    assert res_a.method_count == 3
    assert res_a.median_percentile == 0.90
    assert pytest.approx(res_a.mean_percentile, rel=1e-3) == 0.90
    assert res_a.rank_dispersion is not None

    res_b = next(r for r in results if r.compound_id == "CMPD_B")
    assert res_b.median_percentile == 0.50
    assert pytest.approx(res_b.mean_percentile, rel=1e-3) == 0.50


def test_score_consensus_missing_data_and_weights() -> None:
    percentiles = {
        "CMPD_X": {"chemplp": 0.90, "goldscore": None, "vina": 0.70},
        "CMPD_Y": {"chemplp": None, "goldscore": None, "vina": None},
    }
    weights = {"chemplp": 2.0, "goldscore": 1.0, "vina": 1.0}

    results = compute_score_consensus(
        compound_percentiles=percentiles,
        weights=weights,
    )

    res_x = next(r for r in results if r.compound_id == "CMPD_X")
    assert res_x.method_count == 2
    assert pytest.approx(res_x.median_percentile, rel=1e-3) == 0.80
    # Weighted mean: (2.0*0.90 + 1.0*0.70) / (2.0 + 1.0) = 2.50 / 3.0 = 0.8333
    assert pytest.approx(res_x.weighted_percentile, rel=1e-3) == 2.5 / 3.0

    res_y = next(r for r in results if r.compound_id == "CMPD_Y")
    assert res_y.method_count == 0
    assert res_y.median_percentile is None
    assert res_y.mean_percentile is None
    assert res_y.weighted_percentile is None
