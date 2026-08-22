"""Immutable domain models for adapters, plans, QC, and bundles."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from enum import StrEnum
from typing import Any

from pydantic import Field, field_validator

from fidelichem.domain.chemistry import (
    IdentityResolution,
    SourceSystem,
    SourceValue,
)
from fidelichem.domain.ids import new_id
from fidelichem.domain.models import (
    DomainModel,
    ImportBatch,
    OpaqueId,
    SafeRelativePath,
    Sha256Digest,
    UtcTimestamp,
    _non_blank,
)


class QCSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class QCIssue(DomainModel):
    """An individual quality control observation or diagnostic finding."""

    code: str
    message: str
    severity: QCSeverity = QCSeverity.WARNING
    source_file: SafeRelativePath | None = None
    line_number: int | None = Field(default=None, ge=1, strict=True)
    entity_reference: str | None = None

    _code_not_blank = field_validator("code")(_non_blank)
    _message_not_blank = field_validator("message")(_non_blank)


class ValidationReport(DomainModel):
    """Result of bundle and domain integrity validation."""

    is_valid: bool
    errors: tuple[str, ...] = Field(default_factory=tuple)
    warnings: tuple[str, ...] = Field(default_factory=tuple)
    qc_issues: tuple[QCIssue, ...] = Field(default_factory=tuple)


class DetectionReport(DomainModel):
    """Result of an adapter probe on a candidate source path."""

    confidence: float = Field(ge=0.0, le=1.0)
    detected_format: str
    candidate_files: tuple[str, ...] = Field(default_factory=tuple)
    warnings: tuple[str, ...] = Field(default_factory=tuple)
    requires_user_mapping: bool = False
    suggested_adapter: str
    extra_metadata: Mapping[str, Any] = Field(default_factory=dict)

    _detected_format_not_blank = field_validator("detected_format")(_non_blank)
    _suggested_adapter_not_blank = field_validator("suggested_adapter")(_non_blank)

    @field_validator("confidence")
    @classmethod
    def _validate_finite_confidence(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("confidence must be a finite float")
        return v


def compute_plan_hash(
    adapter_id: str,
    adapter_version: str,
    source_root: str,
    source_files: tuple[str, ...],
    file_hashes: tuple[tuple[str, str], ...],
    options: Mapping[str, Any],
) -> str:
    """Compute deterministic SHA-256 hash of an import plan payload."""
    payload = {
        "adapter_id": adapter_id.strip(),
        "adapter_version": adapter_version.strip(),
        "source_root": source_root.strip(),
        "source_files": sorted(source_files),
        "file_hashes": sorted(file_hashes, key=lambda x: x[0]),
        "options": dict(sorted(options.items())),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class ImportPlan(DomainModel):
    """Immutable, content-hashed blueprint for an import operation."""

    id: OpaqueId = Field(default_factory=new_id)
    adapter_id: str
    adapter_version: str
    source_root: str
    source_files: tuple[str, ...] = Field(default_factory=tuple)
    file_hashes: tuple[tuple[str, Sha256Digest], ...] = Field(default_factory=tuple)
    options: Mapping[str, Any] = Field(default_factory=dict)
    created_at: UtcTimestamp
    plan_hash: Sha256Digest

    _adapter_id_not_blank = field_validator("adapter_id")(_non_blank)
    _adapter_version_not_blank = field_validator("adapter_version")(_non_blank)
    _source_root_not_blank = field_validator("source_root")(_non_blank)


class RawCompoundRecord(DomainModel):
    """Canonical representation of an imported compound and its identity claim."""

    source_system: SourceSystem
    source_value: SourceValue
    source_smiles: str | None = None
    source_inchikey: str | None = None
    preparation_ph: float | None = None
    source_artifact_path: SafeRelativePath | None = None
    metadata: Mapping[str, Any] = Field(default_factory=dict)

    @field_validator("preparation_ph")
    @classmethod
    def _validate_finite_ph(cls, v: float | None) -> float | None:
        if v is not None and not math.isfinite(v):
            raise ValueError("preparation_ph must be a finite float")
        return v


class TargetRecord(DomainModel):
    """Canonical representation of a biological macromolecular target."""

    name: str
    accession: str | None = None
    pdb_id: str | None = None
    chain: str | None = None
    sequence_hash: Sha256Digest | None = None
    notes: str | None = None

    _name_not_blank = field_validator("name")(_non_blank)


class DockingRunRecord(DomainModel):
    """Canonical representation of a computational docking run."""

    run_name: str
    target_name: str | None = None
    engine: str
    engine_version: str | None = None
    configuration_hash: Sha256Digest | None = None
    parameters: Mapping[str, Any] = Field(default_factory=dict)

    _run_name_not_blank = field_validator("run_name")(_non_blank)
    _engine_not_blank = field_validator("engine")(_non_blank)


class PoseRecord(DomainModel):
    """Canonical representation of a 3D ligand binding pose."""

    run_name: str
    compound_source_system: SourceSystem
    compound_source_value: SourceValue
    source_pose_id: str
    rank: int = Field(ge=1, strict=True)
    structure_artifact_path: SafeRelativePath | None = None
    coordinate_hash: Sha256Digest | None = None

    _fields_not_blank = field_validator(
        "run_name",
        "source_pose_id",
    )(_non_blank)


class ScoreObservationRecord(DomainModel):
    """Canonical observation of a computational score for a pose."""

    run_name: str
    compound_source_value: str
    source_pose_id: str
    score_key: str
    raw_value: float
    source_artifact_path: SafeRelativePath | None = None

    _fields_not_blank = field_validator(
        "run_name",
        "compound_source_value",
        "source_pose_id",
        "score_key",
    )(_non_blank)

    @field_validator("raw_value")
    @classmethod
    def _validate_finite_score(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("raw_value must be a finite float")
        return v


class SourceArtifactRecord(DomainModel):
    """Canonical metadata for an imported source file."""

    relative_path: SafeRelativePath
    sha256: Sha256Digest
    size_bytes: int = Field(ge=0, strict=True)
    file_type: str
    mtime: UtcTimestamp | None = None

    _file_type_not_blank = field_validator("file_type")(_non_blank)


class InteractionRecord(DomainModel):
    """Canonical mechanistic molecular interaction between ligand pose and target."""

    run_name: str
    compound_source_value: str
    source_pose_id: str
    residue_name: str
    interaction_type: str
    target_name: str | None = None
    residue_number: int | None = None
    chain: str | None = None
    distance: float | None = None
    angle: float | None = None
    energy: float | None = None
    frequency: float | None = None
    ligand_feature: str | None = None
    metadata: Mapping[str, Any] = Field(default_factory=dict)

    _fields_not_blank = field_validator(
        "run_name",
        "compound_source_value",
        "source_pose_id",
        "residue_name",
        "interaction_type",
    )(_non_blank)

    @property
    def interaction_key(self) -> str:
        """Standard canonical interaction key (target|residue|type)."""
        tgt = self.target_name or "target"
        return f"{tgt}|{self.residue_name}|{self.interaction_type.lower()}"

    @property
    def granular_interaction_key(self) -> str:
        """Granular interaction key including ligand feature."""
        tgt = self.target_name or "target"
        feat = self.ligand_feature or "any"
        return f"{tgt}|{self.residue_name}|{self.interaction_type.lower()}|{feat}"


class ImportBundle(DomainModel):
    """Complete canonical evidence package generated by an adapter parse step."""

    plan: ImportPlan
    targets: tuple[TargetRecord, ...] = Field(default_factory=tuple)
    compounds: tuple[RawCompoundRecord, ...] = Field(default_factory=tuple)
    docking_runs: tuple[DockingRunRecord, ...] = Field(default_factory=tuple)
    poses: tuple[PoseRecord, ...] = Field(default_factory=tuple)
    scores: tuple[ScoreObservationRecord, ...] = Field(default_factory=tuple)
    interactions: tuple[InteractionRecord, ...] = Field(default_factory=tuple)
    source_artifacts: tuple[SourceArtifactRecord, ...] = Field(default_factory=tuple)
    qc_messages: tuple[QCIssue, ...] = Field(default_factory=tuple)
    provenance: Mapping[str, Any] = Field(default_factory=dict)


class ImportResult(DomainModel):
    """Outcome of an import operation executed against a FideliChem project."""

    batch: ImportBatch
    bundle: ImportBundle
    validation: ValidationReport
    confirmed_resolutions: tuple[IdentityResolution, ...] = Field(default_factory=tuple)


__all__ = [
    "DetectionReport",
    "DockingRunRecord",
    "ImportBundle",
    "ImportPlan",
    "ImportResult",
    "InteractionRecord",
    "PoseRecord",
    "QCIssue",
    "QCSeverity",
    "RawCompoundRecord",
    "ScoreObservationRecord",
    "SourceArtifactRecord",
    "TargetRecord",
    "ValidationReport",
    "compute_plan_hash",
]
