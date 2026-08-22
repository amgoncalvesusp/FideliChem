from __future__ import annotations

import json
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import Barrier

import pytest
from sqlalchemy import Engine

from fidelichem.domain.chemistry import (
    IdentityActor,
    IdentityClaim,
    IdentitySelection,
    SelectionMode,
)
from fidelichem.domain.errors import AliasConflictError, IdentityResolutionConflictError
from fidelichem.domain.models import ActorKind, ImportBatch, ImportStatus, Project
from fidelichem.identity.models import (
    CatalogAction,
    ResolutionCandidate,
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


def _service(engine: Engine, failpoint=None) -> IdentityService:
    return IdentityService(
        uow_factory=lambda: UnitOfWork(engine),
        index_factory=lambda: PersistentIdentityIndex(engine),
        clock=lambda: NOW,
        failpoint=failpoint,
    )


def _claim(source_value: str = "ligand-1") -> IdentityClaim:
    return IdentityClaim(
        smiles="CCO",
        source_system="gold",
        source_value=source_value,
        import_batch_id=BATCH_ID,
    )


def _actor() -> IdentityActor:
    return IdentityActor(kind=ActorKind.SYSTEM)


def _user() -> IdentityActor:
    return IdentityActor(
        kind=ActorKind.USER, actor_id="reviewer", rationale="concurrent review"
    )


def _report() -> ResolutionReport:
    return ResolutionReport(
        kind=ResolutionKind.NEW_COMPOUND,
        reason=ResolutionReason.NEW_COMPOUND,
        catalog_action=CatalogAction.CREATE_COMPOUND,
    )


def _result():
    from fidelichem.domain.chemistry import (
        CanonicalizationResult,
        Compound,
        MolecularState,
    )

    return CanonicalizationResult(
        source_smiles="CCO",
        compound=Compound(
            id="33333333-3333-4333-8333-333333333333",
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
            compound_id="33333333-3333-4333-8333-333333333333",
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


def test_concurrent_root_confirmation_has_one_winner_and_one_audit(
    migrated_engine,
) -> None:
    _seed_project_batch(migrated_engine)
    barrier = Barrier(2)

    def confirm() -> object:
        def failpoint(point: str) -> None:
            if point == "before_chemistry":
                barrier.wait(timeout=10)

        return _service(migrated_engine, failpoint=failpoint).confirm_claim(
            _result(),
            _claim(),
            _report(),
            IdentitySelection(mode=SelectionMode.NEW_COMPOUND),
            _actor(),
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: _attempt(confirm), range(2)))
    assert sum(not isinstance(outcome, Exception) for outcome in outcomes) == 1
    assert sum(isinstance(outcome, AliasConflictError) for outcome in outcomes) == 1
    with UnitOfWork(migrated_engine) as uow:
        aliases = uow.aliases.list_by_batch(BATCH_ID)
        assert len(aliases) == 1
        assert len(uow.identity_resolutions.list_by_alias(aliases[0].id)) == 1
        assert len(uow.audit_events.list_by_batch(BATCH_ID)) == 1


def test_concurrent_matching_structure_reuses_winner_with_audited_race(
    migrated_engine,
) -> None:
    _seed_project_batch(migrated_engine)
    barrier = Barrier(2)

    def confirm(source_value: str) -> object:
        def failpoint(point: str) -> None:
            if point == "before_chemistry":
                barrier.wait(timeout=10)

        return _attempt(
            lambda: _service(migrated_engine, failpoint=failpoint).confirm_claim(
                _result(),
                _claim(source_value),
                _report(),
                IdentitySelection(mode=SelectionMode.NEW_COMPOUND),
                _actor(),
            )
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(confirm, ("ligand-1", "ligand-2")))
    assert all(not isinstance(outcome, Exception) for outcome in outcomes)
    with UnitOfWork(migrated_engine) as uow:
        events = uow.audit_events.list_by_batch(BATCH_ID)
        assert len(events) == 2
        reuse_flags = {
            bool(json.loads(event.new_value_json or "{}")["reuse_after_race"])
            for event in events
        }
        assert reuse_flags == {False, True}


def test_concurrent_new_state_race_reuses_one_state_and_audits_both(
    migrated_engine: Engine,
) -> None:
    _seed_project_batch(migrated_engine)
    with UnitOfWork(migrated_engine) as uow:
        uow.compounds.add(_result().compound)
    report = ResolutionReport(
        kind=ResolutionKind.NEW_STATE,
        reason=ResolutionReason.PARENT_MATCH,
        candidates=(
            ResolutionCandidate(compound_id="33333333-3333-4333-8333-333333333333"),
        ),
        catalog_action=CatalogAction.REUSE_COMPOUND,
        catalog_match_dormant=True,
    )
    barrier = Barrier(2)

    def confirm(source_value: str) -> object:
        def failpoint(point: str) -> None:
            if point == "before_state":
                barrier.wait(timeout=10)

        return _attempt(
            lambda: _service(migrated_engine, failpoint=failpoint).confirm_claim(
                _result(),
                _claim(source_value),
                report,
                IdentitySelection(
                    mode=SelectionMode.EXISTING_TARGET,
                    compound_id="33333333-3333-4333-8333-333333333333",
                ),
                _actor(),
            )
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(confirm, ("ligand-1", "ligand-2")))
    assert all(not isinstance(outcome, Exception) for outcome in outcomes)
    with UnitOfWork(migrated_engine) as uow:
        assert uow.molecular_states.get("44444444-4444-4444-8444-444444444444")
        events = uow.audit_events.list_by_batch(BATCH_ID)
        assert len(events) == 2
        assert {
            bool(json.loads(event.new_value_json or "{}")["reuse_after_race"])
            for event in events
        } == {False, True}


def _seed_root(engine: Engine) -> tuple[str, str]:
    _seed_project_batch(engine)
    _service(engine).confirm_claim(
        _result(),
        _claim(),
        _report(),
        IdentitySelection(mode=SelectionMode.NEW_COMPOUND),
        _actor(),
    )
    with UnitOfWork(engine) as uow:
        alias = uow.aliases.list_by_batch(BATCH_ID)[0]
        root = uow.identity_resolutions.list_by_alias(alias.id)[0]
    return alias.id, root.id


@pytest.mark.parametrize("decision", ("reassign", "retract"))
def test_concurrent_transition_has_one_winner_and_no_losing_audit(
    migrated_engine: Engine, decision: str
) -> None:
    alias_id, predecessor_id = _seed_root(migrated_engine)
    barrier = Barrier(2)

    def transition() -> object:
        def failpoint(point: str) -> None:
            if point == "before_transition":
                barrier.wait(timeout=10)

        service = _service(migrated_engine, failpoint=failpoint)
        if decision == "reassign":
            return service.reassign(
                alias_id,
                predecessor_id,
                IdentitySelection(
                    mode=SelectionMode.EXISTING_TARGET,
                    compound_id="33333333-3333-4333-8333-333333333333",
                ),
                _user(),
            )
        return service.retract(alias_id, predecessor_id, _user())

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: _attempt(transition), range(2)))
    assert sum(not isinstance(outcome, Exception) for outcome in outcomes) == 1
    assert (
        sum(
            isinstance(outcome, IdentityResolutionConflictError) for outcome in outcomes
        )
        == 1
    )
    with UnitOfWork(migrated_engine) as uow:
        assert len(uow.identity_resolutions.list_by_alias(alias_id)) == 2
        assert len(uow.audit_events.list_by_batch(BATCH_ID)) == 2


def test_concurrent_restore_has_one_winner_and_no_losing_audit(
    migrated_engine: Engine,
) -> None:
    alias_id, predecessor_id = _seed_root(migrated_engine)
    retracted = _service(migrated_engine).retract(alias_id, predecessor_id, _user())
    barrier = Barrier(2)

    def restore() -> object:
        def failpoint(point: str) -> None:
            if point == "before_transition":
                barrier.wait(timeout=10)

        return _service(migrated_engine, failpoint=failpoint).restore(
            alias_id,
            retracted.id,
            IdentitySelection(
                mode=SelectionMode.EXISTING_TARGET,
                compound_id="33333333-3333-4333-8333-333333333333",
            ),
            _user(),
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: _attempt(restore), range(2)))
    assert sum(not isinstance(outcome, Exception) for outcome in outcomes) == 1
    assert (
        sum(
            isinstance(outcome, IdentityResolutionConflictError) for outcome in outcomes
        )
        == 1
    )
    with UnitOfWork(migrated_engine) as uow:
        assert len(uow.identity_resolutions.list_by_alias(alias_id)) == 3
        assert len(uow.audit_events.list_by_batch(BATCH_ID)) == 3


def _attempt(operation):
    try:
        return operation()
    except Exception as error:  # asserted below as a public typed conflict
        return error
