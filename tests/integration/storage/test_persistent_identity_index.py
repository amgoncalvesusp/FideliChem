from __future__ import annotations

import ast
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import Engine, text

from fidelichem.domain.chemistry import (
    Alias,
    Compound,
    IdentityDecision,
    IdentityResolution,
    MolecularState,
)
from fidelichem.domain.models import ActorKind, ImportBatch, ImportStatus, Project
from fidelichem.identity.models import EvidenceKind
from fidelichem.storage.identity_index import PersistentIdentityIndex
from fidelichem.storage.repositories import CorruptStoredDataError
from fidelichem.storage.session import UnitOfWork, create_session_factory

NOW = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)
PROJECT_ID = "11111111-1111-4111-8111-111111111111"
COMPOUND_ID = "22222222-2222-4222-8222-222222222222"
STATE_A_ID = "33333333-3333-4333-8333-333333333333"
STATE_B_ID = "44444444-4444-4444-8444-444444444444"
ALIAS_ID = "55555555-5555-4555-8555-555555555555"
ROOT_ID = "66666666-6666-4666-8666-666666666666"


def _project() -> Project:
    return Project(id=PROJECT_ID, name="Project", created_at=NOW, updated_at=NOW)


def _batch(project_id: str, batch_id: str, status: ImportStatus) -> ImportBatch:
    return ImportBatch(
        id=batch_id,
        project_id=project_id,
        adapter_id="adapter",
        adapter_version="1",
        started_at=NOW,
        status=status,
        source_root="inputs",
    )


def _compound() -> Compound:
    return Compound(
        id=COMPOUND_ID,
        canonical_smiles="CCO",
        isomeric_smiles="CCO",
        formula="C2H6O",
        molecular_weight=46.069,
        structure_hash="a" * 64,
        inchikey="LFQSCWFLJHTTHZ-UHFFFAOYSA-N",
        chemistry_policy_id="fidelichem.rdkit-identity.v1",
        rdkit_version="2026.3.4",
        inchi_version="1.0.0",
        created_at=NOW,
    )


def _state(state_id: str, digest: str) -> MolecularState:
    return MolecularState(
        id=state_id,
        compound_id=COMPOUND_ID,
        state_smiles="CCO" if state_id == STATE_A_ID else "OCC",
        state_inchikey="LFQSCWFLJHTTHZ-UHFFFAOYSA-N",
        formal_charge=0,
        stereochemistry_signature="none",
        protonation_signature="neutral",
        tautomer_signature="canonical",
        state_hash=digest,
        chemistry_policy_id="fidelichem.rdkit-identity.v1",
        rdkit_version="2026.3.4",
        inchi_version="1.0.0",
        preparation_ph=None,
    )


def _alias(batch_id: str) -> Alias:
    return Alias(
        id=ALIAS_ID,
        source_system="gold",
        source_value="ligand_17",
        import_batch_id=batch_id,
        created_at=NOW,
    )


def _resolution(
    *, decision: IdentityDecision = IdentityDecision.CONFIRMED,
    resolution_id: str = ROOT_ID,
    compound_id: str | None = COMPOUND_ID,
    molecular_state_id: str | None = STATE_A_ID,
    supersedes_id: str | None = None,
    decided_at: datetime = NOW,
) -> IdentityResolution:
    return IdentityResolution(
        id=resolution_id,
        alias_id=ALIAS_ID,
        decision=decision,
        compound_id=compound_id,
        molecular_state_id=molecular_state_id,
        supersedes_id=supersedes_id,
        decided_at=decided_at,
        actor_kind=ActorKind.SYSTEM,
    )


def test_catalog_and_active_projection_reopen_dormant_siblings(
    migrated_engine: Engine,
) -> None:
    project = _project()
    batch = _batch(
        project.id,
        "77777777-7777-4777-8777-777777777777",
        ImportStatus.COMPLETED,
    )
    with UnitOfWork(migrated_engine) as uow:
        uow.projects.add(project)
        uow.import_batches.add(batch)
        uow.compounds.add(_compound())
        uow.molecular_states.add(_state(STATE_A_ID, "b" * 64))
        uow.molecular_states.add(_state(STATE_B_ID, "c" * 64))
        uow.aliases.add(_alias(batch.id))
        uow.identity_resolutions.add(_resolution())
        uow.identity_resolutions.add(
            _resolution(
                decision=IdentityDecision.REASSIGNED,
                resolution_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                supersedes_id=ROOT_ID,
                decided_at=NOW + timedelta(minutes=1),
            )
        )

    index = PersistentIdentityIndex(migrated_engine)
    state_rows = index.catalog_by_state_hash("b" * 64)
    assert len(state_rows) == 1
    assert state_rows[0].molecular_state_id == STATE_A_ID
    assert state_rows[0].catalog_dormant is False
    sibling = index.catalog_by_state_hash("c" * 64)[0]
    assert sibling.catalog_dormant is True
    active = index.active_by_alias("gold", "ligand_17")
    assert len(active) == 1
    assert active[0].molecular_state_id == STATE_A_ID
    assert active[0].resolution_id == "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    assert index.catalog_by_parent_hash("a" * 64)[0].compound_id == COMPOUND_ID
    inchikey_rows = index.catalog_by_generated_inchikey("LFQSCWFLJHTTHZ-UHFFFAOYSA-N")
    assert inchikey_rows
    assert all(EvidenceKind.CATALOG_INCHI in row.evidence for row in inchikey_rows)

    reopened = PersistentIdentityIndex(migrated_engine)
    assert reopened.catalog_by_state_hash("c" * 64) == (sibling,)


def test_compound_only_resolution_dormancy_is_not_inherited_by_siblings(
    migrated_engine: Engine,
) -> None:
    project = _project()
    batch = _batch(
        project.id,
        "88888888-8888-4888-8888-888888888888",
        ImportStatus.COMPLETED,
    )
    with UnitOfWork(migrated_engine) as uow:
        uow.projects.add(project)
        uow.import_batches.add(batch)
        uow.compounds.add(_compound())
        uow.molecular_states.add(_state(STATE_A_ID, "b" * 64))
        uow.molecular_states.add(_state(STATE_B_ID, "c" * 64))
        uow.aliases.add(_alias(batch.id))
        uow.identity_resolutions.add(_resolution(molecular_state_id=None))
    index = PersistentIdentityIndex(migrated_engine)
    assert index.catalog_by_parent_hash("a" * 64)[0].catalog_dormant is False
    assert index.catalog_by_state_hash("b" * 64)[0].catalog_dormant is True
    assert index.catalog_by_state_hash("c" * 64)[0].catalog_dormant is True


def test_retraction_and_rolled_back_batch_hide_active_alias_not_catalog(
    migrated_engine: Engine,
) -> None:
    project = _project()
    batch = _batch(
        project.id,
        "99999999-9999-4999-8999-999999999999",
        ImportStatus.COMPLETED,
    )
    with UnitOfWork(migrated_engine) as uow:
        uow.projects.add(project)
        uow.import_batches.add(batch)
        uow.compounds.add(_compound())
        uow.molecular_states.add(_state(STATE_A_ID, "b" * 64))
        uow.aliases.add(_alias(batch.id))
        uow.identity_resolutions.add(_resolution())
    with UnitOfWork(migrated_engine) as uow:
        uow.identity_resolutions.add(
            _resolution(
                decision=IdentityDecision.RETRACTED,
                resolution_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                compound_id=None,
                molecular_state_id=None,
                supersedes_id=ROOT_ID,
            )
        )
    index = PersistentIdentityIndex(migrated_engine)
    assert index.active_by_alias("gold", "ligand_17") == ()
    assert index.catalog_by_state_hash("b" * 64)


def test_rolled_back_batch_hides_active_projection_but_not_catalog(
    migrated_engine: Engine,
) -> None:
    project = _project()
    batch = _batch(
        project.id,
        "abababab-abab-4bab-8bab-abababababab",
        ImportStatus.COMPLETED,
    )
    with UnitOfWork(migrated_engine) as uow:
        uow.projects.add(project)
        uow.import_batches.add(batch)
        uow.compounds.add(_compound())
        uow.molecular_states.add(_state(STATE_A_ID, "d" * 64))
        uow.aliases.add(_alias(batch.id))
        uow.identity_resolutions.add(_resolution())
    with UnitOfWork(migrated_engine) as uow:
        uow.import_batches.rollback(batch.id, rollback_reason="withdrawn")

    index = PersistentIdentityIndex(migrated_engine)
    assert index.active_by_alias("gold", "ligand_17") == ()
    assert index.catalog_by_state_hash("d" * 64)[0].catalog_dormant is True


def test_index_public_surface_is_select_only() -> None:
    source = (
        Path(__file__).resolve().parents[3]
        / "src/fidelichem/storage/identity_index.py"
    )
    tree = ast.parse(source.read_text(encoding="utf-8"))
    index_class = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "PersistentIdentityIndex"
    )
    public_methods = {
        node.name
        for node in index_class.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and not node.name.startswith("_")
    }
    assert public_methods <= {
        "catalog_by_state_hash",
        "catalog_by_parent_hash",
        "catalog_by_generated_inchikey",
        "active_by_alias",
    }


def test_index_accepts_session_factory(migrated_engine: Engine) -> None:
    index = PersistentIdentityIndex(create_session_factory(migrated_engine))
    assert index.catalog_by_state_hash("missing") == ()


def test_corrupt_catalog_row_maps_to_safe_storage_error(
    migrated_engine: Engine,
) -> None:
    with migrated_engine.connect() as connection:
        connection.execute(text("PRAGMA ignore_check_constraints=ON"))
        connection.execute(
            text(
                "INSERT INTO compound "
                "(id,canonical_smiles,isomeric_smiles,formula,molecular_weight,"
                "structure_hash,chemistry_policy_id,rdkit_version,created_at) "
                "VALUES ('bad','C','C','CH4',1,'bad','v1','rdkit','bad')"
            )
        )
        connection.commit()
    with pytest.raises(CorruptStoredDataError, match="stored compound"):
        PersistentIdentityIndex(migrated_engine).catalog_by_parent_hash("bad")
