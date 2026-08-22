"""Domain models for table importer mapping schemas, column roles, and presets."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, field_validator

from fidelichem.domain.ids import new_id
from fidelichem.domain.models import (
    DomainModel,
    OpaqueId,
    UtcTimestamp,
    _non_blank,
)


class ColumnRole(StrEnum):
    """Semantic role of a column in a tabular evidence file."""

    MOLECULE_ID = "molecule_id"
    MOLECULE_NAME = "molecule_name"
    SMILES = "smiles"
    INCHIKEY = "inchikey"
    TARGET_NAME = "target_name"
    RUN_NAME = "run_name"
    POSE_ID = "pose_id"
    RANK = "rank"
    SCORE = "score"
    PROPERTY = "property"
    METADATA = "metadata"
    IGNORE = "ignore"


class ScoreDirection(StrEnum):
    """Directionality of a score metric."""

    LOWER_BETTER = "lower_better"
    HIGHER_BETTER = "higher_better"
    NEUTRAL = "neutral"


class ScoreScope(StrEnum):
    """Comparability scope of a score observation."""

    RUN = "run"
    TARGET = "target"
    GLOBAL = "global"


class ScoreColumnMapping(DomainModel):
    """Configuration mapping a table column to a canonical score observation."""

    column_name: str
    score_key: str
    direction: ScoreDirection = ScoreDirection.LOWER_BETTER
    unit: str | None = None
    scope: ScoreScope = ScoreScope.RUN
    description: str | None = None

    _column_name_not_blank = field_validator("column_name")(_non_blank)
    _score_key_not_blank = field_validator("score_key")(_non_blank)


class IdentityColumnMapping(DomainModel):
    """Configuration mapping table columns to chemical identity and run metadata."""

    molecule_id_column: str | None = None
    molecule_name_column: str | None = None
    smiles_column: str | None = None
    inchikey_column: str | None = None
    source_system_default: str = "table_import"
    source_system_column: str | None = None
    target_name_default: str | None = None
    target_name_column: str | None = None
    run_name_default: str = "default_run"
    run_name_column: str | None = None
    pose_id_column: str | None = None
    rank_column: str | None = None
    preparation_ph_default: float | None = None
    preparation_ph_column: str | None = None


class TableMappingSchema(DomainModel):
    """Complete specification for parsing and mapping a tabular evidence file."""

    identity: IdentityColumnMapping = Field(default_factory=IdentityColumnMapping)
    scores: tuple[ScoreColumnMapping, ...] = Field(default_factory=tuple)
    property_columns: tuple[str, ...] = Field(default_factory=tuple)
    metadata_columns: tuple[str, ...] = Field(default_factory=tuple)
    delimiter: str | None = None
    has_header: bool = True
    sheet_name: str | None = None
    skip_rows: int = Field(default=0, ge=0)
    comment_prefix: str | None = None


class TableMappingPreset(DomainModel):
    """Reusable, persisted column mapping template for tabular files."""

    id: OpaqueId = Field(default_factory=new_id)
    name: str
    description: str | None = None
    schema_definition: TableMappingSchema
    created_at: UtcTimestamp
    updated_at: UtcTimestamp

    _name_not_blank = field_validator("name")(_non_blank)


__all__ = [
    "ColumnRole",
    "IdentityColumnMapping",
    "ScoreColumnMapping",
    "ScoreDirection",
    "ScoreScope",
    "TableMappingPreset",
    "TableMappingSchema",
]
