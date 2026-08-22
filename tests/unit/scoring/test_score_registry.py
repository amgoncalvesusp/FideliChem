"""Unit tests for ScoreRegistry and scoring function catalog."""

from __future__ import annotations

import pytest

from fidelichem.domain.scoring import (
    ComparabilityScope,
    ScoreDefinition,
    ScoreDirection,
)
from fidelichem.scoring.registry import ScoreRegistry


def test_builtin_scores_registered_by_default() -> None:
    registry = ScoreRegistry.create_default()
    assert registry.has("gold.chemplp")
    assert registry.has("vina.affinity")
    assert registry.has("gold.goldscore")
    assert registry.has("glide.gscore")

    chemplp = registry.get("gold.chemplp")
    assert chemplp.direction == ScoreDirection.HIGHER_BETTER
    assert chemplp.source_engine == "gold"
    assert chemplp.unit == "fitness"

    vina = registry.get("vina.affinity")
    assert vina.direction == ScoreDirection.LOWER_BETTER
    assert vina.source_engine == "vina"
    assert vina.unit == "kcal/mol"


def test_custom_score_registration_and_override() -> None:
    registry = ScoreRegistry()
    assert len(registry.list_definitions()) == 0

    custom = ScoreDefinition(
        key="custom.docking",
        display_name="Custom Docking Score",
        direction=ScoreDirection.LOWER_BETTER,
        comparability_scope=ComparabilityScope.RUN,
    )
    registry.register(custom)
    assert registry.has("custom.docking")
    assert registry.get("custom.docking") is custom

    # Duplicate registration without override fails
    with pytest.raises(ValueError, match="already registered"):
        registry.register(custom)

    # With override
    custom_v2 = ScoreDefinition(
        key="custom.docking",
        display_name="Custom Docking Score V2",
        direction=ScoreDirection.HIGHER_BETTER,
    )
    registry.register(custom_v2, allow_override=True)
    assert registry.get("custom.docking").direction == ScoreDirection.HIGHER_BETTER


def test_resolve_or_infer_fallback() -> None:
    registry = ScoreRegistry.create_default()

    # Known
    d1 = registry.resolve_or_infer("gold.chemplp")
    assert d1.direction == ScoreDirection.HIGHER_BETTER

    # Unknown higher-better heuristic (plp / fitness / score)
    d2 = registry.resolve_or_infer("in_house_plp_fitness")
    assert d2.direction == ScoreDirection.HIGHER_BETTER

    # Unknown lower-better heuristic (affinity / energy / delta_g)
    d3 = registry.resolve_or_infer("binding_energy_kcal")
    assert d3.direction == ScoreDirection.LOWER_BETTER

    # Explicit override in resolve_or_infer
    d4 = registry.resolve_or_infer(
        "mystery_metric", direction=ScoreDirection.HIGHER_BETTER
    )
    assert d4.direction == ScoreDirection.HIGHER_BETTER
