"""Unit tests for scoring domain models, definitions, and statistics."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from fidelichem.domain.scoring import (
    ComparabilityScope,
    NormalizedScoreObservation,
    ScoreDefinition,
    ScoreDirection,
    ScoreDistributionStats,
)


def test_score_definition_model() -> None:
    defn = ScoreDefinition(
        key="gold.chemplp",
        display_name="GOLD ChemPLP Fitness",
        source_engine="gold",
        direction=ScoreDirection.HIGHER_BETTER,
        unit="fitness",
        comparability_scope=ComparabilityScope.RUN,
        description="Empirical fitness scoring function from GOLD docking",
    )
    assert defn.key == "gold.chemplp"
    assert defn.direction == ScoreDirection.HIGHER_BETTER
    assert defn.comparability_scope == ComparabilityScope.RUN
    assert defn.id is not None

    with pytest.raises(ValidationError, match="key"):
        ScoreDefinition(
            key="",
            display_name="Empty Key",
            direction=ScoreDirection.HIGHER_BETTER,
        )


def test_normalized_score_observation_model() -> None:
    norm_obs = NormalizedScoreObservation(
        score_key="vina.affinity",
        raw_value=-9.2,
        direction=ScoreDirection.LOWER_BETTER,
        scope_key="target_1/run_1",
        rank=1,
        percentile=1.0,
        robust_z=2.15,
        standard_z=2.01,
        entity_reference="CMPD_100",
    )
    assert norm_obs.score_key == "vina.affinity"
    assert norm_obs.raw_value == -9.2
    assert norm_obs.rank == 1
    assert norm_obs.percentile == 1.0
    assert norm_obs.robust_z == 2.15


def test_score_distribution_stats_model() -> None:
    stats = ScoreDistributionStats(
        score_key="docking.plp",
        scope_key="target_1/run_1",
        count_total=100,
        count_observed=90,
        count_missing=10,
        min_raw=12.5,
        max_raw=95.0,
        median_raw=60.0,
        q25_raw=45.0,
        q75_raw=75.0,
        iqr_raw=30.0,
        mean_raw=59.5,
        std_raw=15.2,
    )
    assert stats.count_total == 100
    assert stats.count_observed == 90
    assert stats.count_missing == 10
    assert stats.iqr_raw == 30.0
