"""Domain models for multi-fidelity Decision Profiles, criteria, and explanations."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Any

from pydantic import Field, field_validator

from fidelichem.domain.models import DomainModel


def _non_blank(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Field must not be empty or whitespace")
    return value.strip()


class CriterionRole(StrEnum):
    """Functional role of an analytical criterion in candidate triage."""

    MANDATORY = "mandatory"
    EXCLUSION = "exclusion"
    RANK = "rank"
    WARNING = "warning"
    INFORMATIVE = "informative"


class DecisionPriority(StrEnum):
    """Deterministic progression priority assigned to a candidate."""

    ADVANCE = "ADVANCE"
    HOLD = "HOLD"
    REJECT = "REJECT"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class DecisionCriterion(DomainModel):
    """Specification of a single decision rule or evaluation dimension."""

    key: str
    role: CriterionRole
    weight: float = Field(ge=0.0, default=1.0)
    min_value: float | None = None
    max_value: float | None = None
    allowed_values: tuple[str, ...] = Field(default_factory=tuple)
    rejected_values: tuple[str, ...] = Field(default_factory=tuple)
    description: str | None = None

    _key_not_blank = field_validator("key")(_non_blank)


class DecisionProfile(DomainModel):
    """Configurable decision policy schema guiding multi-fidelity compound triage."""

    name: str
    version: int = Field(ge=1, default=1)
    description: str | None = None
    criteria: Mapping[str, DecisionCriterion] = Field(default_factory=dict)
    default_next_evidence_map: Mapping[str, str] = Field(default_factory=dict)

    _name_not_blank = field_validator("name")(_non_blank)


class CompoundDecision(DomainModel):
    """Actionable triage verdict and explanatory audit report for a single compound."""

    compound_id: str
    priority: DecisionPriority
    composite_score: float | None = None
    rank: int | None = None
    why_positive: tuple[str, ...] = Field(default_factory=tuple)
    why_negative: tuple[str, ...] = Field(default_factory=tuple)
    warnings: tuple[str, ...] = Field(default_factory=tuple)
    recommended_next_evidence: tuple[str, ...] = Field(default_factory=tuple)
    evaluations: Mapping[str, Any] = Field(default_factory=dict)

    _compound_id_not_blank = field_validator("compound_id")(_non_blank)


class DecisionCampaignResult(DomainModel):
    """Complete campaign evaluation output containing all prioritized decisions."""

    profile_name: str
    profile_version: int
    total_evaluated: int = Field(ge=0, strict=True)
    advance_count: int = Field(ge=0, strict=True)
    hold_count: int = Field(ge=0, strict=True)
    reject_count: int = Field(ge=0, strict=True)
    decisions: tuple[CompoundDecision, ...] = Field(default_factory=tuple)


__all__ = [
    "CompoundDecision",
    "CriterionRole",
    "DecisionCampaignResult",
    "DecisionCriterion",
    "DecisionPriority",
    "DecisionProfile",
]
