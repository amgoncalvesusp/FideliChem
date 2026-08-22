"""Immutable, storage-independent identity-resolution values."""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum
from typing import Any, Protocol, cast

from pydantic import Field, field_validator, model_validator

from fidelichem.domain.models import DomainModel, OpaqueId


class ResolutionKind(StrEnum):
    EXACT_STATE = "exact_state"
    NEW_STATE = "new_state"
    NEW_COMPOUND = "new_compound"
    ALIAS_ONLY = "alias_only"
    AMBIGUOUS = "ambiguous"
    CONFLICT = "conflict"
    UNRESOLVED = "unresolved"


class ResolutionReason(StrEnum):
    EXACT_STATE = "exact_state"
    PARENT_MATCH = "parent_match"
    NEW_COMPOUND = "new_compound"
    ALIAS_ONLY = "alias_only"
    AMBIGUOUS_ALIAS = "ambiguous_alias"
    CONFLICTING_EVIDENCE = "conflicting_evidence"
    UNRESOLVED = "unresolved"


class EvidenceKind(StrEnum):
    CATALOG_STATE = "catalog_state"
    CATALOG_PARENT = "catalog_parent"
    CATALOG_INCHI = "catalog_inchi"
    ACTIVE_ALIAS = "active_alias"


class CatalogAction(StrEnum):
    REUSE_STATE = "reuse_state"
    REUSE_COMPOUND = "reuse_compound"
    CREATE_COMPOUND = "create_compound"
    NONE = "none"


_EVIDENCE_ORDER = {
    EvidenceKind.CATALOG_STATE: 0,
    EvidenceKind.CATALOG_PARENT: 1,
    EvidenceKind.CATALOG_INCHI: 2,
    EvidenceKind.ACTIVE_ALIAS: 3,
}


def _candidate_sort_key(
    candidate: ResolutionCandidate,
) -> tuple[str, bool, str, bool, str]:
    return (
        candidate.compound_id,
        candidate.molecular_state_id is None,
        candidate.molecular_state_id or "",
        candidate.resolution_id is None,
        candidate.resolution_id or "",
    )


class ResolutionCandidate(DomainModel):
    """One immutable identity target with its independent evidence."""

    compound_id: OpaqueId
    molecular_state_id: OpaqueId | None = None
    resolution_id: OpaqueId | None = None
    evidence: tuple[EvidenceKind, ...] = Field(default_factory=tuple)
    catalog_dormant: bool = False

    @field_validator("evidence", mode="before")
    @classmethod
    def _sort_evidence(cls, value: object) -> tuple[EvidenceKind, ...]:
        items = cast(Iterable[Any], value) if value is not None else ()
        values = tuple(EvidenceKind(item) for item in items)
        return tuple(dict.fromkeys(sorted(values, key=_EVIDENCE_ORDER.__getitem__)))

    @property
    def sort_key(self) -> tuple[str, bool, str, bool, str]:
        return _candidate_sort_key(self)


class ResolutionReport(DomainModel):
    """Immutable resolver output and catalog-reuse authority marker."""

    kind: ResolutionKind
    reason: ResolutionReason
    candidates: tuple[ResolutionCandidate, ...] = Field(default_factory=tuple)
    catalog_action: CatalogAction = CatalogAction.NONE
    catalog_match_dormant: bool = False

    @field_validator("candidates", mode="before")
    @classmethod
    def _sort_candidates(
        cls, value: object
    ) -> tuple[ResolutionCandidate, ...]:
        items = cast(Iterable[Any], value) if value is not None else ()
        candidates = tuple(
            item
            if isinstance(item, ResolutionCandidate)
            else ResolutionCandidate.model_validate(item)
            for item in items
        )
        return tuple(sorted(candidates, key=_candidate_sort_key))

    @model_validator(mode="after")
    def _validate_catalog_action(self) -> ResolutionReport:
        required = {
            ResolutionKind.EXACT_STATE: CatalogAction.REUSE_STATE,
            ResolutionKind.NEW_STATE: CatalogAction.REUSE_COMPOUND,
            ResolutionKind.NEW_COMPOUND: CatalogAction.CREATE_COMPOUND,
        }
        expected = required.get(self.kind)
        if expected is not None and self.catalog_action is not expected:
            raise ValueError("catalog_action does not match resolution kind")
        if self.catalog_match_dormant and self.catalog_action not in {
            CatalogAction.REUSE_STATE,
            CatalogAction.REUSE_COMPOUND,
        }:
            raise ValueError("catalog_match_dormant requires catalog reuse")
        return self


class IdentityIndex(Protocol):
    """Read-only evidence index consumed by the pure resolver."""

    def catalog_by_state_hash(
        self, state_hash: str
    ) -> tuple[ResolutionCandidate, ...]: ...

    def catalog_by_parent_hash(
        self, parent_hash: str
    ) -> tuple[ResolutionCandidate, ...]: ...

    def catalog_by_generated_inchikey(
        self, inchikey: str
    ) -> tuple[ResolutionCandidate, ...]: ...

    def active_by_alias(
        self, source_system: str, source_value: str
    ) -> tuple[ResolutionCandidate, ...]: ...


__all__ = [
    "CatalogAction",
    "EvidenceKind",
    "IdentityIndex",
    "ResolutionCandidate",
    "ResolutionKind",
    "ResolutionReason",
    "ResolutionReport",
]
