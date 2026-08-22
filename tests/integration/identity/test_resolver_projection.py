from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import Engine

from fidelichem.domain.chemistry import (
    Alias,
    CanonicalizationResult,
    Compound,
    IdentityClaim,
    IdentityDecision,
    IdentityResolution,
    MolecularState,
)
from fidelichem.domain.models import ActorKind, ImportBatch, ImportStatus, Project
from fidelichem.identity.models import ResolutionKind
from fidelichem.identity.resolver import IdentityResolver
from fidelichem.storage.engine import create_sqlite_engine
from fidelichem.storage.identity_index import PersistentIdentityIndex
from fidelichem.storage.runner import upgrade_database
from fidelichem.storage.session import UnitOfWork


@pytest.fixture
def migrated_engine(tmp_path: Path) -> Iterator[Engine]:
    engine = create_sqlite_engine(tmp_path / "project.fidelichem.sqlite")
    upgrade_database(engine)
    try:
        yield engine
    finally:
        engine.dispose()

NOW = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)
PROJECT_ID = "11111111-1111-4111-8111-111111111111"
COMPOUND_ID = "22222222-2222-4222-8222-222222222222"
STATE_A_ID = "33333333-3333-4333-8333-333333333333"
STATE_B_ID = "44444444-4444-4444-8444-444444444444"
ALIAS_ID = "55555555-5555-4555-8555-555555555555"
ROOT_ID = "66666666-6666-4666-8666-666666666666"
INCHI = "LFQSCWFLJHTTHZ-UHFFFAOYSA-N"


def _result(*, state_hash: str = "a" * 64) -> CanonicalizationResult:
    compound = Compound(
        id=COMPOUND_ID,
        canonical_smiles="CCO",
        isomeric_smiles="CCO",
        inchikey=INCHI,
        formula="C2H6O",
        molecular_weight=46.069,
        structure_hash="b" * 64,
        chemistry_policy_id="fidelichem.rdkit-identity.v1",
        rdkit_version="2026.3.4",
        inchi_version="1.0.0",
        created_at=NOW,
    )
    state = MolecularState(
        id=STATE_A_ID if state_hash == "a" * 64 else STATE_B_ID,
        compound_id=COMPOUND_ID,
        state_smiles="CCO",
        state_inchikey=INCHI,
        formal_charge=0,
        stereochemistry_signature="stereo",
        protonation_signature="charge",
        tautomer_signature="tautomer",
        state_hash=state_hash,
        chemistry_policy_id="fidelichem.rdkit-identity.v1",
        rdkit_version="2026.3.4",
        inchi_version="1.0.0",
    )
    return CanonicalizationResult(
        source_smiles="CCO",
        compound=compound,
        molecular_state=state,
        chemistry_policy_id="fidelichem.rdkit-identity.v1",
    )


def _claim() -> IdentityClaim:
    return IdentityClaim(
        smiles="CCO",
        source_system="gold",
        source_value="ligand-17",
    )


def _project() -> Project:
    return Project(id=PROJECT_ID, name="Project", created_at=NOW, updated_at=NOW)


def _batch() -> ImportBatch:
    return ImportBatch(
        id="77777777-7777-4777-8777-777777777777",
        project_id=PROJECT_ID,
        adapter_id="adapter",
        adapter_version="1",
        started_at=NOW,
        status=ImportStatus.COMPLETED,
        source_root="inputs",
    )


def _compound() -> Compound:
    return _result().compound


def _state(state_id: str, digest: str) -> MolecularState:
    state = _result(state_hash=digest).molecular_state
    return state.model_copy(update={"id": state_id})


def _root() -> IdentityResolution:
    return IdentityResolution(
        id=ROOT_ID,
        alias_id=ALIAS_ID,
        decision=IdentityDecision.CONFIRMED,
        compound_id=COMPOUND_ID,
        molecular_state_id=STATE_A_ID,
        decided_at=NOW,
        actor_kind=ActorKind.SYSTEM,
    )


def test_reopened_projection_keeps_dormant_exact_state_without_alias_conflict(
    migrated_engine: Engine,
) -> None:
    batch = _batch()
    with UnitOfWork(migrated_engine) as uow:
        uow.projects.add(_project())
        uow.import_batches.add(batch)
        uow.compounds.add(_compound())
        uow.molecular_states.add(_state(STATE_A_ID, "a" * 64))
        uow.aliases.add(
            Alias(
                id=ALIAS_ID,
                source_system="gold",
                source_value="ligand-17",
                import_batch_id=batch.id,
                created_at=NOW,
            )
        )
        uow.identity_resolutions.add(_root())

    with UnitOfWork(migrated_engine) as uow:
        uow.identity_resolutions.add(
            IdentityResolution(
                id="88888888-8888-4888-8888-888888888888",
                alias_id=ALIAS_ID,
                decision=IdentityDecision.RETRACTED,
                supersedes_id=ROOT_ID,
                decided_at=NOW,
                actor_kind=ActorKind.SYSTEM,
            )
        )
        uow.import_batches.rollback(batch.id, rollback_reason="withdrawn")

    index = PersistentIdentityIndex(migrated_engine)
    report = IdentityResolver().resolve(_result(), _claim(), index)
    assert report.kind is ResolutionKind.EXACT_STATE
    assert report.catalog_match_dormant is True
    assert report.candidates[0].catalog_dormant is True


def test_dormant_parent_returns_new_state_and_reuses_compound(
    migrated_engine: Engine,
) -> None:
    batch = _batch()
    with UnitOfWork(migrated_engine) as uow:
        uow.projects.add(_project())
        uow.import_batches.add(batch)
        uow.compounds.add(_compound())
        uow.molecular_states.add(_state(STATE_A_ID, "a" * 64))
        uow.aliases.add(
            Alias(
                id=ALIAS_ID,
                source_system="gold",
                source_value="ligand-17",
                import_batch_id=batch.id,
                created_at=NOW,
            )
        )
        uow.identity_resolutions.add(_root())
    with UnitOfWork(migrated_engine) as uow:
        uow.import_batches.rollback(batch.id, rollback_reason="withdrawn")

    report = IdentityResolver().resolve(
        _result(state_hash="c" * 64),
        _claim(),
        PersistentIdentityIndex(migrated_engine),
    )
    assert report.kind is ResolutionKind.NEW_STATE
    assert report.catalog_match_dormant is True
