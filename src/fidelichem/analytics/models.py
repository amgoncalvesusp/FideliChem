"""Immutable domain models for consensus scoring, agreement, and Pareto analytics."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Any

from pydantic import Field

from fidelichem.domain.models import DomainModel
from fidelichem.domain.table_importer import ScoreDirection


class AgreementLevel(StrEnum):
    """Classification of multi-score or multi-method consistency for a candidate."""

    HIGH = "HIGH"
    MODERATE = "MODERATE"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


class ScoreConsensusResult(DomainModel):
    """Consensus aggregation of multiple scoring methods for a single compound."""

    compound_id: str
    median_percentile: float | None = None
    mean_percentile: float | None = None
    weighted_percentile: float | None = None
    rank_dispersion: float | None = None
    method_count: int = Field(ge=0, strict=True)
    raw_scores: Mapping[str, float | None] = Field(default_factory=dict)
    percentiles: Mapping[str, float | None] = Field(default_factory=dict)
    ranks: Mapping[str, int | None] = Field(default_factory=dict)


class MoleculeAgreement(DomainModel):
    """Per-molecule agreement metrics across multiple scoring methods."""

    compound_id: str
    percentile_range: float | None = None
    percentile_std: float | None = None
    agreement_level: AgreementLevel = AgreementLevel.UNKNOWN
    method_count: int = Field(ge=0, strict=True)


class CampaignAgreement(DomainModel):
    """Global agreement metrics across scoring functions for a project campaign."""

    scoring_methods: tuple[str, ...]
    spearman_matrix: Mapping[str, Mapping[str, float | None]] = Field(
        default_factory=dict
    )
    kendall_matrix: Mapping[str, Mapping[str, float | None]] = Field(
        default_factory=dict
    )
    top_k_overlap: Mapping[str, float] = Field(default_factory=dict)
    pair_counts: Mapping[str, int] = Field(default_factory=dict)


class ParetoFrontierResult(DomainModel):
    """Multi-objective Pareto optimization frontiers and non-dominated ranking."""

    dimensions: tuple[str, ...]
    directions: Mapping[str, ScoreDirection]
    frontier_compounds: tuple[str, ...] = Field(default_factory=tuple)
    dominated_compounds: tuple[str, ...] = Field(default_factory=tuple)
    pareto_ranks: Mapping[str, int] = Field(default_factory=dict)
    candidate_values: Mapping[str, Mapping[str, float | None]] = Field(
        default_factory=dict
    )
    metadata: Mapping[str, Any] = Field(default_factory=dict)


__all__ = [
    "AgreementLevel",
    "CampaignAgreement",
    "MoleculeAgreement",
    "ParetoFrontierResult",
    "ScoreConsensusResult",
]
