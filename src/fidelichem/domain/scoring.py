"""Domain models for score definitions, comparability scopes, and normalized metrics."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, field_validator

from fidelichem.domain.ids import new_id
from fidelichem.domain.models import (
    DomainModel,
    OpaqueId,
    _non_blank,
)


class ScoreDirection(StrEnum):
    """Directionality convention for score ranking and consensus."""

    HIGHER_BETTER = "higher_better"
    LOWER_BETTER = "lower_better"
    TARGET_RANGE = "target_range"
    DESCRIPTIVE = "descriptive"


class ComparabilityScope(StrEnum):
    """Scope of valid statistical comparison and normalization."""

    RUN = "run"
    TARGET = "target"
    GLOBAL = "global"


class ScoreDefinition(DomainModel):
    """Immutable specification of a scoring metric, its unit, direction, and scope."""

    id: OpaqueId = Field(default_factory=new_id)
    key: str
    display_name: str
    source_engine: str | None = None
    direction: ScoreDirection = ScoreDirection.LOWER_BETTER
    unit: str | None = None
    comparability_scope: ComparabilityScope = ComparabilityScope.RUN
    description: str | None = None
    is_builtin: bool = False

    _key_not_blank = field_validator("key")(_non_blank)
    _display_name_not_blank = field_validator("display_name")(_non_blank)


class NormalizedScoreObservation(DomainModel):
    """Relative and normalized statistical representation of a raw score observation."""

    id: OpaqueId = Field(default_factory=new_id)
    score_key: str
    raw_value: float
    direction: ScoreDirection
    scope_key: str
    rank: int = Field(ge=1)
    percentile: float = Field(ge=0.0, le=1.0)
    robust_z: float | None = None
    standard_z: float | None = None
    entity_reference: str | None = None

    _score_key_not_blank = field_validator("score_key")(_non_blank)
    _scope_key_not_blank = field_validator("scope_key")(_non_blank)


class ScoreDistributionStats(DomainModel):
    """Descriptive statistics of a score distribution within a comparability scope."""

    score_key: str
    scope_key: str
    count_total: int = Field(ge=0)
    count_observed: int = Field(ge=0)
    count_missing: int = Field(ge=0)
    min_raw: float | None = None
    max_raw: float | None = None
    median_raw: float | None = None
    q25_raw: float | None = None
    q75_raw: float | None = None
    iqr_raw: float | None = None
    mean_raw: float | None = None
    std_raw: float | None = None

    _score_key_not_blank = field_validator("score_key")(_non_blank)
    _scope_key_not_blank = field_validator("scope_key")(_non_blank)


__all__ = [
    "ComparabilityScope",
    "NormalizedScoreObservation",
    "ScoreDefinition",
    "ScoreDirection",
    "ScoreDistributionStats",
]
