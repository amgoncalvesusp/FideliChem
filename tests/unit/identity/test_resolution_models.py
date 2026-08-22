from __future__ import annotations

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


def test_identity_index_is_a_read_only_protocol() -> None:
    assert hasattr(IdentityIndex, "catalog_by_state_hash")
    assert not any(
        name in dir(IdentityIndex)
        for name in ("add", "save", "commit", "write", "delete")
    )
