"""Immutable chemistry and identity values independent of RDKit."""

from __future__ import annotations

from enum import StrEnum
from re import fullmatch
from typing import Annotated

from pydantic import (
    AfterValidator,
    BeforeValidator,
    Field,
    FiniteFloat,
    model_validator,
)

from .ids import new_id
from .models import ActorKind, DomainModel, OpaqueId, Sha256Digest, UtcTimestamp


def _non_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("value must not be blank")
    return value


def _bounded_text(value: str, *, limit: int, field: str) -> str:
    if "\x00" in value:
        raise ValueError(f"{field} must not contain NUL")
    if not value.strip():
        raise ValueError(f"{field} must not be blank")
    if len(value) > limit:
        raise ValueError(f"{field} exceeds its maximum length")
    return value


def _source_value(value: str) -> str:
    return _bounded_text(value, limit=1024, field="source_value")


def _source_system(value: str) -> str:
    if len(value) > 128 or fullmatch(r"[a-z0-9][a-z0-9._-]*", value) is None:
        raise ValueError("source_system must be a lowercase slug")
    return value


def _actor_id(value: str) -> str:
    return _bounded_text(value, limit=128, field="actor_id")


def _rationale(value: str) -> str:
    return _bounded_text(value, limit=1024, field="rationale")


def _reject_bool(value: object) -> object:
    if isinstance(value, bool):
        raise ValueError("numeric value must not be boolean")
    return value


def _inchi_key(value: str) -> str:
    if len(value) != 27 or value[14] != "-" or value[25] != "-":
        raise ValueError("inchi key has an invalid format")
    uppercase = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    if not (
        all(character in uppercase for character in value[:14])
        and all(character in uppercase for character in value[15:25])
        and value[26] in uppercase
    ):
        raise ValueError("inchi key has an invalid format")
    return value


NonBlankText = Annotated[str, AfterValidator(_non_blank)]
InchiKey = Annotated[str, AfterValidator(_inchi_key)]
SourceSystem = Annotated[
    str,
    AfterValidator(_source_system),
]
SourceValue = Annotated[str, AfterValidator(_source_value)]
ActorId = Annotated[str, AfterValidator(_actor_id)]
Rationale = Annotated[str, AfterValidator(_rationale)]
FinitePositive = Annotated[
    FiniteFloat,
    BeforeValidator(_reject_bool),
    Field(gt=0),
]
FinitePh = Annotated[
    FiniteFloat,
    BeforeValidator(_reject_bool),
    Field(ge=0, le=14),
]


class IdentityDecision(StrEnum):
    CONFIRMED = "confirmed"
    REASSIGNED = "reassigned"
    RETRACTED = "retracted"
    RESTORED = "restored"


class ChemistryWarningCode(StrEnum):
    INCHI_UNAVAILABLE = "inchi_unavailable"


class SelectionMode(StrEnum):
    EXISTING_TARGET = "existing_target"
    NEW_COMPOUND = "new_compound"


class Compound(DomainModel):
    id: OpaqueId = Field(default_factory=new_id)
    canonical_smiles: NonBlankText
    isomeric_smiles: NonBlankText
    inchikey: InchiKey | None = None
    formula: NonBlankText
    molecular_weight: FinitePositive
    structure_hash: Sha256Digest
    chemistry_policy_id: NonBlankText
    rdkit_version: NonBlankText
    inchi_version: NonBlankText | None = None
    created_at: UtcTimestamp


class MolecularState(DomainModel):
    id: OpaqueId = Field(default_factory=new_id)
    compound_id: OpaqueId
    state_smiles: NonBlankText
    state_inchikey: InchiKey | None = None
    formal_charge: int = Field(strict=True)
    stereochemistry_signature: NonBlankText
    protonation_signature: NonBlankText
    tautomer_signature: NonBlankText
    state_hash: Sha256Digest
    chemistry_policy_id: NonBlankText
    rdkit_version: NonBlankText
    inchi_version: NonBlankText | None = None
    preparation_ph: FinitePh | None = None


class Alias(DomainModel):
    id: OpaqueId = Field(default_factory=new_id)
    source_system: SourceSystem
    source_value: SourceValue
    import_batch_id: OpaqueId
    created_at: UtcTimestamp


class IdentityResolution(DomainModel):
    id: OpaqueId = Field(default_factory=new_id)
    alias_id: OpaqueId
    decision: IdentityDecision
    compound_id: OpaqueId | None = None
    molecular_state_id: OpaqueId | None = None
    supersedes_id: OpaqueId | None = None
    decided_at: UtcTimestamp
    actor_kind: ActorKind
    actor_id: ActorId | None = None
    rationale: Rationale | None = None

    @model_validator(mode="after")
    def _validate_decision_shape(self) -> IdentityResolution:
        if self.decision is IdentityDecision.CONFIRMED:
            if self.compound_id is None or self.supersedes_id is not None:
                raise ValueError("confirmed resolution has an invalid target shape")
        elif self.decision is IdentityDecision.REASSIGNED:
            if self.compound_id is None or self.supersedes_id is None:
                raise ValueError("reassigned resolution has an invalid target shape")
        elif self.decision is IdentityDecision.RETRACTED:
            if (
                self.compound_id is not None
                or self.molecular_state_id is not None
                or self.supersedes_id is None
            ):
                raise ValueError("retracted resolution has an invalid target shape")
        elif self.decision is IdentityDecision.RESTORED and (
            self.compound_id is None
            or self.supersedes_id is None
            or self.actor_kind is not ActorKind.USER
            or self.rationale is None
        ):
            raise ValueError("restored resolution has an invalid target shape")
        return self

    @model_validator(mode="after")
    def _validate_actor_shape(self) -> IdentityResolution:
        if self.actor_kind is ActorKind.SYSTEM and self.actor_id is not None:
            raise ValueError("system actor must not have actor_id")
        if self.actor_kind is ActorKind.USER and self.actor_id is None:
            raise ValueError("user actor requires actor_id")
        return self


class ChemistryWarning(DomainModel):
    code: ChemistryWarningCode
    message: NonBlankText


class CanonicalizationResult(DomainModel):
    source_smiles: str
    compound: Compound
    molecular_state: MolecularState
    chemistry_policy_id: NonBlankText
    warnings: tuple[ChemistryWarning, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def _validate_policy_consistency(self) -> CanonicalizationResult:
        if (
            self.compound.chemistry_policy_id != self.chemistry_policy_id
            or self.molecular_state.chemistry_policy_id != self.chemistry_policy_id
        ):
            raise ValueError("chemistry policy must match all canonical values")
        return self


class IdentityClaim(DomainModel):
    source_system: SourceSystem | None = None
    source_value: SourceValue | None = None
    smiles: str | None = None
    inchikey: InchiKey | None = None
    import_batch_id: OpaqueId | None = None

    @model_validator(mode="after")
    def _validate_source_pair(self) -> IdentityClaim:
        if (self.source_system is None) != (self.source_value is None):
            raise ValueError("source_system and source_value must be supplied together")
        return self


class IdentitySelection(DomainModel):
    mode: SelectionMode
    compound_id: OpaqueId | None = None
    molecular_state_id: OpaqueId | None = None

    @model_validator(mode="after")
    def _validate_selection_shape(self) -> IdentitySelection:
        if self.mode is SelectionMode.NEW_COMPOUND:
            if self.compound_id is not None or self.molecular_state_id is not None:
                raise ValueError("new_compound selection must not have target IDs")
        elif self.compound_id is None:
            raise ValueError("existing_target selection requires compound_id")
        return self


class IdentityActor(DomainModel):
    kind: ActorKind
    actor_id: ActorId | None = None
    rationale: Rationale | None = None

    @model_validator(mode="after")
    def _validate_actor(self) -> IdentityActor:
        if self.kind is ActorKind.SYSTEM and self.actor_id is not None:
            raise ValueError("system actor must not have actor_id")
        if self.kind is ActorKind.USER and self.actor_id is None:
            raise ValueError("user actor requires actor_id")
        return self


__all__ = [
    "Alias",
    "CanonicalizationResult",
    "ChemistryWarning",
    "ChemistryWarningCode",
    "Compound",
    "IdentityActor",
    "IdentityClaim",
    "IdentityDecision",
    "IdentityResolution",
    "IdentitySelection",
    "InchiKey",
    "MolecularState",
    "SelectionMode",
    "SourceSystem",
]
