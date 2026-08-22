from __future__ import annotations

import ast
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

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
    *,
    alias_id: str = ALIAS_ID,
    decision: IdentityDecision = IdentityDecision.CONFIRMED,
    resolution_id: str = ROOT_ID,
    compound_id: str | None = COMPOUND_ID,
    molecular_state_id: str | None = STATE_A_ID,
    supersedes_id: str | None = None,
    decided_at: datetime = NOW,
) -> IdentityResolution:
    return IdentityResolution(
        id=resolution_id,
        alias_id=alias_id,
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
    assert [row.molecular_state_id for row in inchikey_rows] == [
        STATE_A_ID,
        STATE_B_ID,
        None,
    ]

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


def test_active_alias_order_is_state_first_and_null_state_last(
    migrated_engine: Engine,
) -> None:
    project = _project()
    first_batch = _batch(
        project.id,
        "12121212-1212-4212-8212-121212121212",
        ImportStatus.COMPLETED,
    )
    second_batch = _batch(
        project.id,
        "13131313-1313-4313-8313-131313131313",
        ImportStatus.COMPLETED,
    )
    second_alias_id = "14141414-1414-4414-8414-141414141414"
    with UnitOfWork(migrated_engine) as uow:
        uow.projects.add(project)
        uow.import_batches.add(first_batch)
        uow.import_batches.add(second_batch)
        uow.compounds.add(_compound())
        uow.molecular_states.add(_state(STATE_A_ID, "a" * 64))
        uow.aliases.add(_alias(first_batch.id))
        uow.aliases.add(
            Alias(
                id=second_alias_id,
                source_system="gold",
                source_value="ligand_17",
                import_batch_id=second_batch.id,
                created_at=NOW,
            )
        )
        uow.identity_resolutions.add(_resolution())
        uow.identity_resolutions.add(
            _resolution(
                alias_id=second_alias_id,
                resolution_id="15151515-1515-4515-8515-151515151515",
                molecular_state_id=None,
            )
        )

    active = PersistentIdentityIndex(migrated_engine).active_by_alias(
        "gold", "ligand_17"
    )
    assert [candidate.molecular_state_id for candidate in active] == [
        STATE_A_ID,
        None,
    ]


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
    assert index.catalog_by_state_hash("b" * 64)[0].catalog_dormant is True
    assert index.catalog_by_parent_hash("a" * 64)[0].catalog_dormant is True
    assert all(
        row.catalog_dormant
        for row in index.catalog_by_generated_inchikey(
            "LFQSCWFLJHTTHZ-UHFFFAOYSA-N"
        )
    )


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
    assert index.catalog_by_parent_hash("a" * 64)[0].catalog_dormant is True
    assert all(
        row.catalog_dormant
        for row in index.catalog_by_generated_inchikey(
            "LFQSCWFLJHTTHZ-UHFFFAOYSA-N"
        )
    )


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
    forbidden_calls = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr
        in {"add", "commit", "delete", "flush", "insert", "text", "update"}
    }
    forbidden_calls.update(
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"delete", "insert", "text", "update"}
    )
    assert forbidden_calls == set()
    assert not any(
        token in source.read_text(encoding="utf-8").lower().split()
        for token in ("insert", "update", "delete")
    )


def test_index_accepts_session_factory(migrated_engine: Engine) -> None:
    index = PersistentIdentityIndex(create_session_factory(migrated_engine))
    assert index.catalog_by_state_hash("missing") == ()


def test_index_closes_each_owned_session(migrated_engine: Engine) -> None:
    closed: list[bool] = []

    class TrackingSession(Session):
        def close(self) -> None:
            closed.append(True)
            super().close()

    factory = sessionmaker(
        bind=migrated_engine,
        class_=TrackingSession,
        autoflush=False,
        expire_on_commit=False,
    )
    assert PersistentIdentityIndex(factory).catalog_by_state_hash("missing") == ()
    assert closed == [True]


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


def test_corrupt_compound_value_is_not_reduced_to_an_id_candidate(
    migrated_engine: Engine,
) -> None:
    project = _project()
    batch = _batch(
        project.id,
        "cdcdcdcd-cdcd-4dcd-8dcd-cdcdcdcdcdcd",
        ImportStatus.COMPLETED,
    )
    with UnitOfWork(migrated_engine) as uow:
        uow.projects.add(project)
        uow.import_batches.add(batch)
        uow.compounds.add(_compound())
        uow.molecular_states.add(_state(STATE_A_ID, "b" * 64))
        uow.aliases.add(_alias(batch.id))
        uow.identity_resolutions.add(_resolution())
    with migrated_engine.connect() as connection:
        connection.execute(text("PRAGMA ignore_check_constraints=ON"))
        connection.execute(
            text(
                "INSERT INTO compound "
                "(id,canonical_smiles,isomeric_smiles,formula,molecular_weight,"
                "structure_hash,chemistry_policy_id,rdkit_version,created_at) "
                "VALUES (:id,'CC','CC','',40,:hash,'policy','rdkit',:created)"
            ),
            {
                "id": "abababab-abab-4bab-8bab-abababababab",
                "hash": "d" * 64,
                "created": "2026-08-22T12:00:00Z",
            },
        )
        connection.commit()

    with pytest.raises(CorruptStoredDataError, match="stored compound"):
        PersistentIdentityIndex(migrated_engine).catalog_by_parent_hash("d" * 64)


def test_corrupt_resolution_value_is_not_reduced_to_an_active_id_candidate(
    migrated_engine: Engine,
) -> None:
    project = _project()
    batch = _batch(
        project.id,
        "dededede-dede-4ded-8ded-dededededede",
        ImportStatus.COMPLETED,
    )
    with UnitOfWork(migrated_engine) as uow:
        uow.projects.add(project)
        uow.import_batches.add(batch)
        uow.compounds.add(_compound())
        uow.molecular_states.add(_state(STATE_A_ID, "b" * 64))
        uow.aliases.add(_alias(batch.id))
        uow.identity_resolutions.add(_resolution())
    with migrated_engine.connect() as connection:
        connection.execute(text("PRAGMA ignore_check_constraints=ON"))
        connection.execute(
            text(
                "INSERT INTO identity_resolution "
                "(id,alias_id,decision,compound_id,molecular_state_id,"
                "supersedes_id,decided_at,actor_kind) VALUES "
                "(:id,:alias,:decision,:compound,:state,:supersedes,:decided,:actor)"
            ),
            {
                "id": "abababab-abab-4bab-8bab-abababababab",
                "alias": ALIAS_ID,
                "decision": "corrupt",
                "compound": COMPOUND_ID,
                "state": STATE_A_ID,
                "supersedes": ROOT_ID,
                "decided": "2026-08-22T12:01:00Z",
                "actor": "system",
            },
        )
        connection.commit()

    with pytest.raises(CorruptStoredDataError, match="stored identity resolution"):
        PersistentIdentityIndex(migrated_engine).active_by_alias("gold", "ligand_17")


def test_corrupt_molecular_state_value_is_not_reduced_to_an_id_candidate(
    migrated_engine: Engine,
) -> None:
    project = _project()
    batch = _batch(
        project.id,
        "fcfcfcfc-fcfc-4fcf-8fcf-fcfcfcfcfcfc",
        ImportStatus.COMPLETED,
    )
    with UnitOfWork(migrated_engine) as uow:
        uow.projects.add(project)
        uow.import_batches.add(batch)
        uow.compounds.add(_compound())
    with migrated_engine.connect() as connection:
        connection.execute(text("PRAGMA ignore_check_constraints=ON"))
        connection.execute(
            text(
                "INSERT INTO molecular_state "
                "(id,compound_id,state_smiles,formal_charge,"
                "stereochemistry_signature,protonation_signature,"
                "tautomer_signature,state_hash,chemistry_policy_id,rdkit_version) "
                "VALUES (:id,:compound,'CC',0,'','neutral','canonical',"
                ":hash,'policy','rdkit')"
            ),
            {
                "id": STATE_A_ID,
                "compound": COMPOUND_ID,
                "hash": "f" * 64,
            },
        )
        connection.commit()

    with pytest.raises(CorruptStoredDataError, match="stored molecular state"):
        PersistentIdentityIndex(migrated_engine).catalog_by_state_hash("f" * 64)


def test_state_with_missing_compound_owner_is_corruption_not_empty_result(
    migrated_engine: Engine,
) -> None:
    with migrated_engine.connect() as connection:
        connection.execute(text("PRAGMA foreign_keys=OFF"))
        connection.execute(text("PRAGMA ignore_check_constraints=ON"))
        connection.execute(
            text(
                "INSERT INTO molecular_state "
                "(id,compound_id,state_smiles,formal_charge,"
                "stereochemistry_signature,protonation_signature,"
                "tautomer_signature,state_hash,chemistry_policy_id,rdkit_version) "
                "VALUES (:id,'missing-owner','CC',0,'stereo','neutral','canonical',"
                ":hash,'policy','rdkit')"
            ),
            {"id": STATE_A_ID, "hash": "a" * 64},
        )
        connection.commit()

    with pytest.raises(CorruptStoredDataError, match="stored molecular state"):
        PersistentIdentityIndex(migrated_engine).catalog_by_state_hash("a" * 64)


def test_corrupt_contributor_cannot_make_catalog_candidate_look_active(
    migrated_engine: Engine,
) -> None:
    project = _project()
    batch = _batch(
        project.id,
        "fdfdfdfd-fdfd-4fdf-8fdf-fdfdfdfdfdfd",
        ImportStatus.COMPLETED,
    )
    with UnitOfWork(migrated_engine) as uow:
        uow.projects.add(project)
        uow.import_batches.add(batch)
        uow.compounds.add(_compound())
        uow.molecular_states.add(_state(STATE_A_ID, "a" * 64))
        uow.aliases.add(_alias(batch.id))
        uow.identity_resolutions.add(_resolution())
    with migrated_engine.connect() as connection:
        connection.execute(text("PRAGMA ignore_check_constraints=ON"))
        connection.execute(
            text(
                "INSERT INTO identity_resolution "
                "(id,alias_id,decision,compound_id,molecular_state_id,"
                "supersedes_id,decided_at,actor_kind) VALUES "
                "(:id,:alias,'corrupt',:compound,:state,:supersedes,:decided,'system')"
            ),
            {
                "id": "abababab-abab-4bab-8bab-abababababab",
                "alias": ALIAS_ID,
                "compound": COMPOUND_ID,
                "state": STATE_A_ID,
                "supersedes": ROOT_ID,
                "decided": "2026-08-22T12:01:00Z",
            },
        )
        connection.commit()

    with pytest.raises(CorruptStoredDataError, match="stored identity resolution"):
        PersistentIdentityIndex(migrated_engine).catalog_by_state_hash("a" * 64)


def test_reopen_uses_a_new_engine_and_keeps_dormant_catalog_rows(
    migrated_engine: Engine,
) -> None:
    project = _project()
    batch = _batch(
        project.id,
        "efefefef-efef-4efe-8efe-efefefefefef",
        ImportStatus.COMPLETED,
    )
    with UnitOfWork(migrated_engine) as uow:
        uow.projects.add(project)
        uow.import_batches.add(batch)
        uow.compounds.add(_compound())
        uow.molecular_states.add(_state(STATE_A_ID, "e" * 64))
        uow.molecular_states.add(_state(STATE_B_ID, "f" * 64))
        uow.aliases.add(_alias(batch.id))
        uow.identity_resolutions.add(_resolution())
    with UnitOfWork(migrated_engine) as uow:
        uow.identity_resolutions.add(
            _resolution(
                decision=IdentityDecision.RETRACTED,
                resolution_id="abababab-abab-4bab-8bab-abababababab",
                compound_id=None,
                molecular_state_id=None,
                supersedes_id=ROOT_ID,
            )
        )
        uow.import_batches.rollback(batch.id, rollback_reason="withdrawn")

    database_url = migrated_engine.url
    migrated_engine.dispose()
    from sqlalchemy import create_engine

    reopened_engine = create_engine(database_url)
    try:
        index = PersistentIdentityIndex(reopened_engine)
        assert index.active_by_alias("gold", "ligand_17") == ()
        assert index.catalog_by_parent_hash("a" * 64)[0].catalog_dormant is True
        assert index.catalog_by_state_hash("e" * 64)[0].catalog_dormant is True
        assert index.catalog_by_state_hash("f" * 64)[0].catalog_dormant is True
        inchikey_rows = index.catalog_by_generated_inchikey(
            "LFQSCWFLJHTTHZ-UHFFFAOYSA-N"
        )
        assert inchikey_rows
        assert all(row.catalog_dormant for row in inchikey_rows)
    finally:
        reopened_engine.dispose()
