from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import Engine

from fidelichem.domain.chemistry import (
    CanonicalizationResult,
    Compound,
    IdentityActor,
    IdentityClaim,
    IdentitySelection,
    MolecularState,
    SelectionMode,
)
from fidelichem.domain.models import ActorKind, ImportBatch, ImportStatus, Project
from fidelichem.identity.models import (
    CatalogAction,
    ResolutionKind,
    ResolutionReason,
    ResolutionReport,
)
from fidelichem.identity.service import IdentityService
from fidelichem.storage.engine import create_sqlite_engine
from fidelichem.storage.identity_index import PersistentIdentityIndex
from fidelichem.storage.runner import upgrade_database
from fidelichem.storage.session import UnitOfWork

NOW = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)
PROJECT_ID = "11111111-1111-4111-8111-111111111111"
BATCH_ID = "22222222-2222-4222-8222-222222222222"
COMPOUND_ID = "33333333-3333-4333-8333-333333333333"


@pytest.fixture
def migrated_engine(tmp_path: Path) -> Iterator[Engine]:
    engine = create_sqlite_engine(tmp_path / "project.fidelichem.sqlite")
    upgrade_database(engine)
    try:
        yield engine
    finally:
        engine.dispose()


def _seed_project_batch(engine: Engine) -> None:
    with UnitOfWork(engine) as uow:
        uow.projects.add(
            Project(id=PROJECT_ID, name="Identity", created_at=NOW, updated_at=NOW)
        )
        uow.import_batches.add(
            ImportBatch(
                id=BATCH_ID,
                project_id=PROJECT_ID,
                adapter_id="adapter",
                adapter_version="1",
                started_at=NOW,
                completed_at=NOW,
                status=ImportStatus.COMPLETED,
                source_root="inputs",
            )
        )


def _service(engine: Engine) -> IdentityService:
    return IdentityService(
        uow_factory=lambda: UnitOfWork(engine),
        index_factory=lambda: PersistentIdentityIndex(engine),
        clock=lambda: NOW,
    )


def _claim() -> IdentityClaim:
    return IdentityClaim(
        smiles="CCO",
        source_system="gold",
        source_value="ligand-1",
        import_batch_id=BATCH_ID,
    )


def _actor(kind: ActorKind = ActorKind.SYSTEM) -> IdentityActor:
    return IdentityActor(
        kind=kind,
        actor_id=None if kind is ActorKind.SYSTEM else "reviewer",
        rationale=None if kind is ActorKind.SYSTEM else "confirmed by review",
    )


def _report() -> ResolutionReport:
    return ResolutionReport(
        kind=ResolutionKind.NEW_COMPOUND,
        reason=ResolutionReason.NEW_COMPOUND,
        catalog_action=CatalogAction.CREATE_COMPOUND,
    )


def _result() -> CanonicalizationResult:
    return CanonicalizationResult(
        source_smiles="CCO",
        compound=Compound(
            id=COMPOUND_ID,
            canonical_smiles="CCO",
            isomeric_smiles="CCO",
            inchikey="LFQSCWFLJHTTHZ-UHFFFAOYSA-N",
            formula="C2H6O",
            molecular_weight=46.069,
            structure_hash="b" * 64,
            chemistry_policy_id="fidelichem.rdkit-identity.v1",
            rdkit_version="2026.3.4",
            inchi_version="1.0.0",
            created_at=NOW,
        ),
        molecular_state=MolecularState(
            id="44444444-4444-4444-8444-444444444444",
            compound_id=COMPOUND_ID,
            state_smiles="CCO",
            state_inchikey="LFQSCWFLJHTTHZ-UHFFFAOYSA-N",
            formal_charge=0,
            stereochemistry_signature="stereo",
            protonation_signature="charge",
            tautomer_signature="tautomer",
            state_hash="a" * 64,
            chemistry_policy_id="fidelichem.rdkit-identity.v1",
            rdkit_version="2026.3.4",
            inchi_version="1.0.0",
        ),
        chemistry_policy_id="fidelichem.rdkit-identity.v1",
    )


def test_audit_payload_is_canonical_and_batch_correlated(migrated_engine) -> None:
    _seed_project_batch(migrated_engine)
    _service(migrated_engine).confirm_claim(
        _result(),
        _claim(),
        _report(),
        IdentitySelection(mode=SelectionMode.NEW_COMPOUND),
        _actor(),
    )
    from fidelichem.storage.session import UnitOfWork

    with UnitOfWork(migrated_engine) as uow:
        event = uow.audit_events.list_by_batch(BATCH_ID)[0]
        assert event.import_batch_id == BATCH_ID
        assert event.old_value_json is None
        assert event.new_value_json == json.dumps(
            json.loads(event.new_value_json or "{}"),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        payload = json.loads(event.new_value_json or "{}")
        assert payload["selected_target"] == {
            "compound_id": COMPOUND_ID,
            "molecular_state_id": "44444444-4444-4444-8444-444444444444",
        }
        assert payload["rationale"] is None
        assert payload["actor_id"] is None


def test_reassignment_audit_contains_prior_and_new_target(migrated_engine) -> None:
    _seed_project_batch(migrated_engine)
    service = _service(migrated_engine)
    service.confirm_claim(
        _result(),
        _claim(),
        _report(),
        IdentitySelection(mode=SelectionMode.NEW_COMPOUND),
        _actor(),
    )
    from fidelichem.storage.session import UnitOfWork

    with UnitOfWork(migrated_engine) as uow:
        alias = uow.aliases.list_by_batch(BATCH_ID)[0]
        root = uow.identity_resolutions.list_by_alias(alias.id)[0]
    service.reassign(
        alias.id,
        root.id,
        IdentitySelection(mode=SelectionMode.EXISTING_TARGET, compound_id=COMPOUND_ID),
        _actor(ActorKind.USER),
    )
    with UnitOfWork(migrated_engine) as uow:
        event = uow.audit_events.list_by_batch(BATCH_ID)[1]
        payload = json.loads(event.new_value_json or "{}")
        assert payload["prior_target"] == {
            "compound_id": COMPOUND_ID,
            "molecular_state_id": "44444444-4444-4444-8444-444444444444",
        }
        assert payload["selected_target"] == {
            "compound_id": COMPOUND_ID,
            "molecular_state_id": None,
        }
