"""Unit tests for multi-objective Pareto frontier and non-dominated sorting."""

from __future__ import annotations

from fidelichem.analytics.pareto import compute_pareto_fronts
from fidelichem.domain.table_importer import ScoreDirection


def test_pareto_2d_front() -> None:
    # 2 objectives: docking (higher=better) and sa_score (lower=better)
    candidates = {
        "A": {"docking": 90.0, "sa_score": 2.0},  # Rank 1 (best docking)
        "B": {"docking": 70.0, "sa_score": 1.5},  # Rank 1 (best SA)
        "C": {"docking": 80.0, "sa_score": 1.8},  # Rank 1 (trade-off)
        "D": {"docking": 60.0, "sa_score": 3.0},  # Dominated by A, B, C (Rank 2)
        "E": {"docking": 50.0, "sa_score": 4.0},  # Dominated by D (Rank 3)
    }

    directions = {
        "docking": ScoreDirection.HIGHER_BETTER,
        "sa_score": ScoreDirection.LOWER_BETTER,
    }

    res = compute_pareto_fronts(
        candidates=candidates,
        dimensions=("docking", "sa_score"),
        directions=directions,
    )

    assert set(res.frontier_compounds) == {"A", "B", "C"}
    assert res.pareto_ranks["A"] == 1
    assert res.pareto_ranks["B"] == 1
    assert res.pareto_ranks["C"] == 1
    assert res.pareto_ranks["D"] == 2
    assert res.pareto_ranks["E"] == 3


def test_pareto_missing_data_preservation() -> None:
    candidates = {
        "A": {"docking": 90.0, "sa_score": 2.0},
        "B": {"docking": 95.0, "sa_score": None},  # missing SA
        "C": {"docking": 85.0, "sa_score": 1.8},
    }
    directions = {
        "docking": ScoreDirection.HIGHER_BETTER,
        "sa_score": ScoreDirection.LOWER_BETTER,
    }

    res = compute_pareto_fronts(
        candidates=candidates,
        dimensions=("docking", "sa_score"),
        directions=directions,
    )

    # A and C are complete non-dominated candidates
    assert "A" in res.frontier_compounds
    assert "C" in res.frontier_compounds
    # B has missing dimension and must not dominate A/C
    assert res.pareto_ranks["B"] > 1
