from __future__ import annotations

import ast
from pathlib import Path

import pytest
from pydantic import ValidationError

from fidelichem.identity.models import (
    CatalogAction,
    EvidenceKind,
    IdentityIndex,
    ResolutionCandidate,
    ResolutionKind,
    ResolutionReason,
    ResolutionReport,
)

COMPOUND = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
STATE = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
RESOLUTION = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"


def test_resolution_values_are_frozen_and_evidence_is_canonical() -> None:
    candidate = ResolutionCandidate(
        compound_id=COMPOUND,
        molecular_state_id=STATE,
        resolution_id=RESOLUTION,
        evidence=(EvidenceKind.ACTIVE_ALIAS, EvidenceKind.CATALOG_STATE),
        catalog_dormant=True,
    )
    assert candidate.evidence == (
        EvidenceKind.CATALOG_STATE,
        EvidenceKind.ACTIVE_ALIAS,
    )
    with pytest.raises((ValidationError, TypeError)):
        candidate.compound_id = STATE


def test_candidate_requires_compound_and_report_action_matches_kind() -> None:
    with pytest.raises(ValidationError):
        ResolutionCandidate(compound_id="not-an-id")
    report = ResolutionReport(
        kind=ResolutionKind.EXACT_STATE,
        reason=ResolutionReason.EXACT_STATE,
        candidates=(
            ResolutionCandidate(
                compound_id=COMPOUND,
                molecular_state_id=STATE,
                evidence=(EvidenceKind.CATALOG_STATE,),
            ),
        ),
        catalog_action=CatalogAction.REUSE_STATE,
        catalog_match_dormant=True,
    )
    assert report.catalog_match_dormant is True
    with pytest.raises(ValidationError):
        ResolutionReport(
            kind=ResolutionKind.NEW_COMPOUND,
            reason=ResolutionReason.NEW_COMPOUND,
            catalog_action=CatalogAction.REUSE_STATE,
        )
    with pytest.raises(ValidationError):
        ResolutionReport(
            kind=ResolutionKind.NEW_COMPOUND,
            reason=ResolutionReason.NEW_COMPOUND,
            catalog_action=CatalogAction.CREATE_COMPOUND,
            catalog_match_dormant=True,
        )


@pytest.mark.parametrize(
    ("kind", "action"),
    [
        (ResolutionKind.EXACT_STATE, CatalogAction.REUSE_STATE),
        (ResolutionKind.NEW_STATE, CatalogAction.REUSE_COMPOUND),
        (ResolutionKind.NEW_COMPOUND, CatalogAction.CREATE_COMPOUND),
        (ResolutionKind.ALIAS_ONLY, CatalogAction.NONE),
        (ResolutionKind.AMBIGUOUS, CatalogAction.NONE),
        (ResolutionKind.CONFLICT, CatalogAction.NONE),
        (ResolutionKind.UNRESOLVED, CatalogAction.NONE),
    ],
)
def test_report_action_is_exhaustive_for_every_resolution_kind(
    kind: ResolutionKind, action: CatalogAction
) -> None:
    report = ResolutionReport(
        kind=kind,
        reason=ResolutionReason.UNRESOLVED,
        catalog_action=action,
    )
    assert report.catalog_action is action
    if action is CatalogAction.REUSE_COMPOUND:
        dormant_report = ResolutionReport(
            kind=ResolutionKind.NEW_STATE,
            reason=ResolutionReason.UNRESOLVED,
            catalog_action=CatalogAction.REUSE_COMPOUND,
            catalog_match_dormant=True,
        )
        assert dormant_report.catalog_match_dormant is True


@pytest.mark.parametrize("kind", list(ResolutionKind))
def test_report_rejects_non_authoritative_action_for_every_kind(
    kind: ResolutionKind,
) -> None:
    with pytest.raises(ValidationError):
        ResolutionReport(
            kind=kind,
            reason=ResolutionReason.UNRESOLVED,
            catalog_action=(
                CatalogAction.REUSE_STATE
                if kind is not ResolutionKind.EXACT_STATE
                else CatalogAction.NONE
            ),
        )


def test_report_candidates_are_sorted_deterministically() -> None:
    later = ResolutionCandidate(
        compound_id=COMPOUND,
        molecular_state_id=None,
        resolution_id=None,
        evidence=(EvidenceKind.CATALOG_PARENT,),
    )
    earlier = ResolutionCandidate(
        compound_id=COMPOUND,
        molecular_state_id=STATE,
        resolution_id=RESOLUTION,
        evidence=(EvidenceKind.CATALOG_STATE,),
    )
    report = ResolutionReport(
        kind=ResolutionKind.EXACT_STATE,
        reason=ResolutionReason.EXACT_STATE,
        candidates=(later, earlier),
        catalog_action=CatalogAction.REUSE_STATE,
    )
    assert report.candidates == (earlier, later)
    tied = ResolutionCandidate(
        compound_id=COMPOUND,
        molecular_state_id=STATE,
        resolution_id=None,
    )
    assert ResolutionReport(
        kind=ResolutionKind.EXACT_STATE,
        reason=ResolutionReason.EXACT_STATE,
        candidates=(tied, earlier),
        catalog_action=CatalogAction.REUSE_STATE,
    ).candidates == (earlier, tied)


def test_identity_index_is_a_read_only_protocol() -> None:
    assert hasattr(IdentityIndex, "catalog_by_state_hash")
    assert not any(
        name in dir(IdentityIndex)
        for name in ("add", "save", "commit", "write", "delete")
    )


def test_identity_models_have_no_storage_or_resolver_imports() -> None:
    source = Path(__file__).resolve().parents[3] / "src/fidelichem/identity/models.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    imported_modules = {
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    imported_modules.update(
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    )
    assert not any(
        module.startswith(("sqlalchemy", "fidelichem.storage"))
        or module.endswith("resolver")
        for module in imported_modules
    )
