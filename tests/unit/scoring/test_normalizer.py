"""Unit tests for ScoreNormalizer, directionality, and robust Z-scores."""

from __future__ import annotations

from fidelichem.domain.scoring import (
    ScoreDefinition,
    ScoreDirection,
)
from fidelichem.scoring.normalizer import ScoreNormalizer


def test_percentile_and_rank_higher_better() -> None:
    normalizer = ScoreNormalizer()
    defn = ScoreDefinition(
        key="gold.chemplp",
        display_name="GOLD ChemPLP",
        direction=ScoreDirection.HIGHER_BETTER,
    )

    # 4 compounds with raw ChemPLP fitness (higher is better)
    raw_entries = [
        {"entity": "C1", "raw": 90.0},
        {"entity": "C2", "raw": 70.0},
        {"entity": "C3", "raw": 50.0},
        {"entity": "C4", "raw": 30.0},
    ]

    normalized, stats = normalizer.normalize_values(
        raw_entries,
        definition=defn,
        scope_key="target_1/run_1",
        value_key="raw",
        entity_key="entity",
    )

    assert stats.count_total == 4
    assert stats.count_observed == 4
    assert stats.count_missing == 0
    assert stats.min_raw == 30.0
    assert stats.max_raw == 90.0
    assert stats.median_raw == 60.0

    # C1 is highest -> rank 1, percentile 1.0
    c1 = next(n for n in normalized if n.entity_reference == "C1")
    assert c1.rank == 1
    assert c1.percentile == 1.0
    assert c1.raw_value == 90.0

    # C4 is lowest -> rank 4, percentile 0.0
    c4 = next(n for n in normalized if n.entity_reference == "C4")
    assert c4.rank == 4
    assert c4.percentile == 0.0


def test_percentile_and_rank_lower_better() -> None:
    normalizer = ScoreNormalizer()
    defn = ScoreDefinition(
        key="vina.affinity",
        display_name="Vina Affinity",
        direction=ScoreDirection.LOWER_BETTER,
    )

    # 4 compounds with raw Vina binding affinity (lower is better: -10.0 is best)
    raw_entries = [
        {"entity": "L1", "raw": -10.0},
        {"entity": "L2", "raw": -8.0},
        {"entity": "L3", "raw": -6.0},
        {"entity": "L4", "raw": -4.0},
    ]

    normalized, stats = normalizer.normalize_values(
        raw_entries,
        definition=defn,
        scope_key="target_1/vina_run",
        value_key="raw",
        entity_key="entity",
    )

    assert stats.min_raw == -10.0
    assert stats.max_raw == -4.0

    # L1 (-10.0 kcal/mol) is best -> rank 1, percentile 1.0
    l1 = next(n for n in normalized if n.entity_reference == "L1")
    assert l1.rank == 1
    assert l1.percentile == 1.0
    assert l1.raw_value == -10.0

    # L4 (-4.0 kcal/mol) is worst -> rank 4, percentile 0.0
    l4 = next(n for n in normalized if n.entity_reference == "L4")
    assert l4.rank == 4
    assert l4.percentile == 0.0


def test_normalization_handles_missing_values_and_ties_safely() -> None:
    normalizer = ScoreNormalizer()
    defn = ScoreDefinition(
        key="test.score",
        display_name="Test Metric",
        direction=ScoreDirection.HIGHER_BETTER,
    )

    # Entries with missing (None) and ties (80.0, 80.0)
    raw_entries = [
        {"entity": "T1", "raw": 80.0},
        {"entity": "T2", "raw": 80.0},
        {"entity": "T3", "raw": None},  # Missing
        {"entity": "T4", "raw": 40.0},
    ]

    normalized, stats = normalizer.normalize_values(
        raw_entries,
        definition=defn,
        scope_key="scope_x",
        value_key="raw",
        entity_key="entity",
    )

    assert stats.count_total == 4
    assert stats.count_observed == 3
    assert stats.count_missing == 1

    # T3 (None) must NOT be present in normalized observations (missing raw preserved)
    entities = {n.entity_reference for n in normalized}
    assert "T3" not in entities
    assert len(normalized) == 3

    # Ties: T1 and T2 both have rank 1 and percentile 1.0
    t1 = next(n for n in normalized if n.entity_reference == "T1")
    t2 = next(n for n in normalized if n.entity_reference == "T2")
    assert t1.rank == 1
    assert t2.rank == 1
    assert t1.percentile == 1.0
    assert t2.percentile == 1.0

    t4 = next(n for n in normalized if n.entity_reference == "T4")
    assert t4.rank == 3
    assert t4.percentile == 0.0


def test_single_element_normalization() -> None:
    normalizer = ScoreNormalizer()
    defn = ScoreDefinition(
        key="single.metric",
        display_name="Single Element",
        direction=ScoreDirection.HIGHER_BETTER,
    )

    raw_entries = [{"entity": "Solo", "raw": 42.0}]
    normalized, stats = normalizer.normalize_values(
        raw_entries,
        definition=defn,
        scope_key="scope_solo",
        value_key="raw",
        entity_key="entity",
    )

    assert len(normalized) == 1
    assert normalized[0].rank == 1
    assert normalized[0].percentile == 1.0
    assert normalized[0].robust_z == 0.0
