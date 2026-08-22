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
MISSING_COMPOUND_ID = "99999999-9999-4999-8999-999999999999"
MISSING_STATE_ID = "aaaaaaaa-9999-4999-8999-999999999999"


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
    assert sibling.catalog_dormant is True, "State B must remain dormant"
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


def test_valid_three_node_chain_returns_active_leaf_and_catalog_candidate(
    migrated_engine: Engine,
) -> None:
    project = _project()
    batch = _batch(
        project.id,
        "70707070-7070-4070-8070-707070707070",
        ImportStatus.COMPLETED,
    )
    middle_id = "71717171-7171-4171-8171-717171717171"
    leaf_id = "72727272-7272-4272-8272-727272727272"
    with UnitOfWork(migrated_engine) as uow:
        uow.projects.add(project)
        uow.import_batches.add(batch)
        uow.compounds.add(_compound())
        uow.molecular_states.add(_state(STATE_A_ID, "a" * 64))
        uow.molecular_states.add(_state(STATE_B_ID, "b" * 64))
        uow.aliases.add(_alias(batch.id))
        uow.identity_resolutions.add(_resolution())
        uow.identity_resolutions.add(
            _resolution(
                resolution_id=middle_id,
                decision=IdentityDecision.REASSIGNED,
                molecular_state_id=STATE_B_ID,
                supersedes_id=ROOT_ID,
                decided_at=NOW + timedelta(minutes=1),
            )
        )
        uow.identity_resolutions.add(
            _resolution(
                resolution_id=leaf_id,
                decision=IdentityDecision.REASSIGNED,
                molecular_state_id=STATE_A_ID,
                supersedes_id=middle_id,
                decided_at=NOW + timedelta(minutes=2),
            )
        )

    index = PersistentIdentityIndex(migrated_engine)
    active = index.active_by_alias("gold", "ligand_17")
    assert len(active) == 1
    assert active[0].resolution_id == leaf_id
    assert active[0].molecular_state_id == STATE_A_ID
    catalog = index.catalog_by_state_hash("b" * 64)
    assert len(catalog) == 1
    assert catalog[0].catalog_dormant is True
    leaf_catalog = index.catalog_by_state_hash("a" * 64)
    assert leaf_catalog[0].catalog_dormant is False


def test_valid_retracted_then_restored_chain_returns_restored_leaf(
    migrated_engine: Engine,
) -> None:
    project = _project()
    batch = _batch(
        project.id,
        "73737373-7373-4373-8373-737373737373",
        ImportStatus.COMPLETED,
    )
    retracted_id = "74747474-7474-4474-8474-747474747474"
    restored_id = "75757575-7575-4575-8575-757575757575"
    with UnitOfWork(migrated_engine) as uow:
        uow.projects.add(project)
        uow.import_batches.add(batch)
        uow.compounds.add(_compound())
        uow.molecular_states.add(_state(STATE_A_ID, "a" * 64))
        uow.molecular_states.add(_state(STATE_B_ID, "b" * 64))
        uow.aliases.add(_alias(batch.id))
        uow.identity_resolutions.add(_resolution())
        uow.identity_resolutions.add(
            _resolution(
                resolution_id=retracted_id,
                decision=IdentityDecision.RETRACTED,
                compound_id=None,
                molecular_state_id=None,
                supersedes_id=ROOT_ID,
                decided_at=NOW + timedelta(minutes=1),
            )
        )
        uow.identity_resolutions.add(
            IdentityResolution(
                id=restored_id,
                alias_id=ALIAS_ID,
                decision=IdentityDecision.RESTORED,
                compound_id=COMPOUND_ID,
                molecular_state_id=STATE_B_ID,
                supersedes_id=retracted_id,
                decided_at=NOW + timedelta(minutes=2),
                actor_kind=ActorKind.USER,
                actor_id="reviewer",
                rationale="reviewed",
            )
        )

    index = PersistentIdentityIndex(migrated_engine)
    active = index.active_by_alias("gold", "ligand_17")
    assert len(active) == 1
    assert active[0].resolution_id == restored_id
    assert active[0].molecular_state_id == STATE_B_ID
    assert index.catalog_by_state_hash("b" * 64)[0].catalog_dormant is False


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


def test_active_alias_order_duplicate_resolution_ids_state_first_null_last(
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
    third_batch = _batch(
        project.id,
        "20202020-2020-4020-8020-202020202020",
        ImportStatus.COMPLETED,
    )
    second_alias_id = "14141414-1414-4414-8414-141414141414"
    third_alias_id = "21212121-2121-4121-8121-212121212121"
    with UnitOfWork(migrated_engine) as uow:
        uow.projects.add(project)
        uow.import_batches.add(first_batch)
        uow.import_batches.add(second_batch)
        uow.import_batches.add(third_batch)
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
        uow.aliases.add(
            Alias(
                id=third_alias_id,
                source_system="gold",
                source_value="ligand_17",
                import_batch_id=third_batch.id,
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
        uow.identity_resolutions.add(
            _resolution(
                alias_id=third_alias_id,
                resolution_id="20202020-2020-4020-8020-202020202020",
            )
        )

    active = PersistentIdentityIndex(migrated_engine).active_by_alias(
        "gold", "ligand_17"
    )
    assert [candidate.molecular_state_id for candidate in active] == [
        STATE_A_ID,
        STATE_A_ID,
        None,
    ]
    assert [candidate.resolution_id for candidate in active[:2]] == [
        "20202020-2020-4020-8020-202020202020",
        ROOT_ID,
    ]


def test_active_alias_order_is_compound_then_state_then_resolution(
    migrated_engine: Engine,
) -> None:
    project = _project()
    first_batch = _batch(
        project.id,
        "16161616-1616-4616-8616-161616161616",
        ImportStatus.COMPLETED,
    )
    second_batch = _batch(
        project.id,
        "17171717-1717-4717-8717-171717171717",
        ImportStatus.COMPLETED,
    )
    second_alias_id = "18181818-1818-4818-8818-181818181818"
    second_compound_id = "11111111-1111-4111-8111-111111111111"
    second_resolution_id = "19191919-1919-4919-8919-191919191919"
    second_compound = Compound(
        id=second_compound_id,
        canonical_smiles="CCN",
        isomeric_smiles="CCN",
        formula="C2H7N",
        molecular_weight=45.085,
        structure_hash="d" * 64,
        inchikey="LFQSCWFLJHTTHZ-UHFFFAOYSA-N",
        chemistry_policy_id="fidelichem.rdkit-identity.v1",
        rdkit_version="2026.3.4",
        inchi_version="1.0.0",
        created_at=NOW,
    )
    with UnitOfWork(migrated_engine) as uow:
        uow.projects.add(project)
        uow.import_batches.add(first_batch)
        uow.import_batches.add(second_batch)
        uow.compounds.add(_compound())
        uow.compounds.add(second_compound)
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
                resolution_id=second_resolution_id,
                compound_id=second_compound_id,
                molecular_state_id=None,
            )
        )

    active = PersistentIdentityIndex(migrated_engine).active_by_alias(
        "gold", "ligand_17"
    )
    assert [
        (candidate.compound_id, candidate.molecular_state_id) for candidate in active
    ] == [
        (second_compound_id, None),
        (COMPOUND_ID, STATE_A_ID),
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
        uow.molecular_states.add(_state(STATE_B_ID, "c" * 64))
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
    assert index.catalog_by_state_hash("c" * 64)[0].catalog_dormant is True
    assert index.catalog_by_parent_hash("a" * 64)[0].catalog_dormant is True
    assert all(
        row.catalog_dormant
        for row in index.catalog_by_generated_inchikey("LFQSCWFLJHTTHZ-UHFFFAOYSA-N")
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
        uow.molecular_states.add(_state(STATE_B_ID, "e" * 64))
        uow.aliases.add(_alias(batch.id))
        uow.identity_resolutions.add(_resolution())
    with UnitOfWork(migrated_engine) as uow:
        uow.import_batches.rollback(batch.id, rollback_reason="withdrawn")

    index = PersistentIdentityIndex(migrated_engine)
    assert index.active_by_alias("gold", "ligand_17") == ()
    assert index.catalog_by_state_hash("d" * 64)[0].catalog_dormant is True
    assert index.catalog_by_state_hash("e" * 64)[0].catalog_dormant is True
    assert index.catalog_by_parent_hash("a" * 64)[0].catalog_dormant is True
    assert all(
        row.catalog_dormant
        for row in index.catalog_by_generated_inchikey("LFQSCWFLJHTTHZ-UHFFFAOYSA-N")
    )


def test_index_public_surface_is_select_only() -> None:
    source = (
        Path(__file__).resolve().parents[3] / "src/fidelichem/storage/identity_index.py"
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
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id in {"connection", "session"}
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
    assert "exec_driver_sql" not in source.read_text(encoding="utf-8")


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
                "(id,compound_id,state_smiles,state_inchikey,formal_charge,"
                "stereochemistry_signature,protonation_signature,"
                "tautomer_signature,state_hash,chemistry_policy_id,rdkit_version) "
                "VALUES (:id,'missing-owner','CC',:inchikey,0,'stereo','neutral',"
                "'canonical',"
                ":hash,'policy','rdkit')"
            ),
            {
                "id": STATE_A_ID,
                "hash": "a" * 64,
                "inchikey": "LFQSCWFLJHTTHZ-UHFFFAOYSA-N",
            },
        )
        connection.commit()

    with pytest.raises(CorruptStoredDataError, match="stored molecular state"):
        PersistentIdentityIndex(migrated_engine).catalog_by_state_hash("a" * 64)
    with pytest.raises(CorruptStoredDataError, match="stored molecular state"):
        PersistentIdentityIndex(migrated_engine).catalog_by_generated_inchikey(
            "LFQSCWFLJHTTHZ-UHFFFAOYSA-N"
        )


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


def test_corrupt_retracted_successor_is_not_hidden_by_active_filter(
    migrated_engine: Engine,
) -> None:
    project = _project()
    batch = _batch(
        project.id,
        "fefefefe-fefe-4fef-8fef-fefefefefefe",
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
                "(:id,:alias,'retracted',:compound,:state,:supersedes,:decided,'system')"
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
        PersistentIdentityIndex(migrated_engine).active_by_alias("gold", "ligand_17")


def test_deep_retracted_chain_corruption_is_safe_in_active_and_catalog(
    migrated_engine: Engine,
) -> None:
    project = _project()
    batch = _batch(
        project.id,
        "edededed-eded-4ede-8ede-edededededed",
        ImportStatus.COMPLETED,
    )
    child_id = "abababab-abab-4bab-8bab-abababababab"
    second_id = "cdcdcdcd-cdcd-4dcd-8dcd-cdcdcdcdcdcd"
    with UnitOfWork(migrated_engine) as uow:
        uow.projects.add(project)
        uow.import_batches.add(batch)
        uow.compounds.add(_compound())
        uow.molecular_states.add(_state(STATE_A_ID, "a" * 64))
        uow.aliases.add(_alias(batch.id))
        uow.identity_resolutions.add(_resolution())
        uow.identity_resolutions.add(
            _resolution(
                decision=IdentityDecision.RETRACTED,
                resolution_id=child_id,
                compound_id=None,
                molecular_state_id=None,
                supersedes_id=ROOT_ID,
            )
        )

    with migrated_engine.connect() as connection:
        connection.execute(text("PRAGMA ignore_check_constraints=ON"))
        connection.execute(text("DROP TRIGGER trg_identity_resolution_validate_insert"))
        connection.execute(
            text(
                "INSERT INTO identity_resolution "
                "(id,alias_id,decision,compound_id,molecular_state_id,"
                "supersedes_id,decided_at,actor_kind) VALUES "
                "(:id,:alias,'retracted',NULL,NULL,:supersedes,:decided,'corrupt')"
            ),
            {
                "id": second_id,
                "alias": ALIAS_ID,
                "supersedes": child_id,
                "decided": "2026-08-22T12:02:00Z",
            },
        )
        connection.commit()

    index = PersistentIdentityIndex(migrated_engine)
    with pytest.raises(CorruptStoredDataError, match="stored identity resolution"):
        index.active_by_alias("gold", "ligand_17")
    with pytest.raises(CorruptStoredDataError, match="stored identity resolution"):
        index.catalog_by_state_hash("a" * 64)


def test_retracted_only_corruption_is_not_hidden_by_active_filter(
    migrated_engine: Engine,
) -> None:
    project = _project()
    batch = _batch(
        project.id,
        "bdbdbdbd-bdbd-4bdb-8bdb-bdbdbdbdbdbd",
        ImportStatus.COMPLETED,
    )
    alias_id = "bebebebe-bebe-4ebe-8ebe-bebebebebebe"
    with UnitOfWork(migrated_engine) as uow:
        uow.projects.add(project)
        uow.import_batches.add(batch)
        uow.aliases.add(
            Alias(
                id=alias_id,
                source_system="gold",
                source_value="retracted-only-corrupt",
                import_batch_id=batch.id,
                created_at=NOW,
            )
        )
    with migrated_engine.connect() as connection:
        connection.execute(text("PRAGMA ignore_check_constraints=ON"))
        connection.execute(text("DROP TRIGGER trg_identity_resolution_validate_insert"))
        connection.execute(
            text(
                "INSERT INTO identity_resolution "
                "(id,alias_id,decision,compound_id,molecular_state_id,"
                "decided_at,actor_kind) "
                "VALUES ('bfbfbfbf-bfbf-4fbf-8fbf-bfbfbfbfbfbf',:alias,'retracted',"
                "NULL,NULL,:decided,'corrupt')"
            ),
            {"alias": alias_id, "decided": "2026-08-22T12:00:00Z"},
        )
        connection.commit()

    with pytest.raises(CorruptStoredDataError, match="stored identity resolution"):
        PersistentIdentityIndex(migrated_engine).active_by_alias(
            "gold", "retracted-only-corrupt"
        )


def test_corrupt_root_is_found_through_full_predecessor_chain(
    migrated_engine: Engine,
) -> None:
    project = _project()
    batch = _batch(
        project.id,
        "c1c1c1c1-c1c1-41c1-81c1-c1c1c1c1c1c1",
        ImportStatus.COMPLETED,
    )
    middle_id = "c2c2c2c2-c2c2-42c2-82c2-c2c2c2c2c2c2"
    leaf_id = "c3c3c3c3-c3c3-43c3-83c3-c3c3c3c3c3c3"
    with UnitOfWork(migrated_engine) as uow:
        uow.projects.add(project)
        uow.import_batches.add(batch)
        uow.compounds.add(_compound())
        uow.molecular_states.add(_state(STATE_A_ID, "a" * 64))
        uow.molecular_states.add(_state(STATE_B_ID, "b" * 64))
        uow.aliases.add(_alias(batch.id))
    with migrated_engine.connect() as connection:
        connection.execute(text("PRAGMA ignore_check_constraints=ON"))
        connection.execute(text("DROP TRIGGER trg_identity_resolution_validate_insert"))
        for row in (
            {
                "id": ROOT_ID,
                "decision": "confirmed",
                "compound": COMPOUND_ID,
                "state": STATE_A_ID,
                "supersedes": None,
                "actor": "corrupt",
            },
            {
                "id": middle_id,
                "decision": "reassigned",
                "compound": COMPOUND_ID,
                "state": STATE_A_ID,
                "supersedes": ROOT_ID,
                "actor": "system",
            },
            {
                "id": leaf_id,
                "decision": "reassigned",
                "compound": COMPOUND_ID,
                "state": STATE_B_ID,
                "supersedes": middle_id,
                "actor": "system",
            },
        ):
            connection.execute(
                text(
                    "INSERT INTO identity_resolution "
                    "(id,alias_id,decision,compound_id,molecular_state_id,"
                    "supersedes_id,decided_at,actor_kind) VALUES "
                    "(:id,:alias,:decision,:compound,:state,:supersedes,"
                    ":decided,:actor)"
                ),
                {
                    **row,
                    "alias": ALIAS_ID,
                    "decided": "2026-08-22T12:00:00Z",
                },
            )
        connection.commit()

    index = PersistentIdentityIndex(migrated_engine)
    with pytest.raises(CorruptStoredDataError, match="stored identity resolution"):
        index.active_by_alias("gold", "ligand_17")
    with pytest.raises(CorruptStoredDataError, match="stored identity resolution"):
        index.catalog_by_state_hash("b" * 64)


def test_successor_with_missing_alias_is_not_invisible(
    migrated_engine: Engine,
) -> None:
    project = _project()
    batch = _batch(
        project.id,
        "c4c4c4c4-c4c4-44c4-84c4-c4c4c4c4c4c4",
        ImportStatus.COMPLETED,
    )
    missing_alias_id = "c5c5c5c5-c5c5-45c5-85c5-c5c5c5c5c5c5"
    successor_id = "c6c6c6c6-c6c6-46c6-86c6-c6c6c6c6c6c6"
    with UnitOfWork(migrated_engine) as uow:
        uow.projects.add(project)
        uow.import_batches.add(batch)
        uow.compounds.add(_compound())
        uow.molecular_states.add(_state(STATE_A_ID, "a" * 64))
        uow.aliases.add(_alias(batch.id))
        uow.identity_resolutions.add(_resolution())
    with migrated_engine.connect() as connection:
        connection.execute(text("PRAGMA foreign_keys=OFF"))
        connection.execute(text("PRAGMA ignore_check_constraints=ON"))
        connection.execute(text("DROP TRIGGER trg_identity_resolution_validate_insert"))
        connection.execute(
            text(
                "INSERT INTO identity_resolution "
                "(id,alias_id,decision,compound_id,molecular_state_id,"
                "supersedes_id,decided_at,actor_kind) VALUES "
                "(:id,:alias,'reassigned',:compound,:state,:supersedes,:decided,'system')"
            ),
            {
                "id": successor_id,
                "alias": missing_alias_id,
                "compound": COMPOUND_ID,
                "state": STATE_A_ID,
                "supersedes": ROOT_ID,
                "decided": "2026-08-22T12:01:00Z",
            },
        )
        connection.commit()

    index = PersistentIdentityIndex(migrated_engine)
    with pytest.raises(CorruptStoredDataError, match="stored identity resolution"):
        index.active_by_alias("gold", "ligand_17")
    with pytest.raises(CorruptStoredDataError, match="stored identity resolution"):
        index.catalog_by_state_hash("a" * 64)


def test_successor_with_missing_batch_is_not_invisible(
    migrated_engine: Engine,
) -> None:
    project = _project()
    batch = _batch(
        project.id,
        "c7c7c7c7-c7c7-47c7-87c7-c7c7c7c7c7c7",
        ImportStatus.COMPLETED,
    )
    orphan_alias_id = "c8c8c8c8-c8c8-48c8-88c8-c8c8c8c8c8c8"
    successor_id = "c9c9c9c9-c9c9-49c9-89c9-c9c9c9c9c9c9"
    missing_batch_id = "d0d0d0d0-d0d0-40d0-80d0-d0d0d0d0d0d0"
    with UnitOfWork(migrated_engine) as uow:
        uow.projects.add(project)
        uow.import_batches.add(batch)
        uow.compounds.add(_compound())
        uow.molecular_states.add(_state(STATE_A_ID, "a" * 64))
        uow.aliases.add(_alias(batch.id))
        uow.identity_resolutions.add(_resolution())
    with migrated_engine.connect() as connection:
        connection.execute(text("PRAGMA foreign_keys=OFF"))
        connection.execute(text("PRAGMA ignore_check_constraints=ON"))
        connection.execute(text("DROP TRIGGER trg_identity_resolution_validate_insert"))
        connection.execute(
            text(
                "INSERT INTO alias "
                "(id,source_system,source_value,import_batch_id,created_at) "
                "VALUES (:id,'gold','orphan-batch',:batch,:created)"
            ),
            {
                "id": orphan_alias_id,
                "batch": missing_batch_id,
                "created": "2026-08-22T12:00:00Z",
            },
        )
        connection.execute(
            text(
                "INSERT INTO identity_resolution "
                "(id,alias_id,decision,compound_id,molecular_state_id,"
                "supersedes_id,decided_at,actor_kind) VALUES "
                "(:id,:alias,'reassigned',:compound,:state,:supersedes,:decided,'system')"
            ),
            {
                "id": successor_id,
                "alias": orphan_alias_id,
                "compound": COMPOUND_ID,
                "state": STATE_A_ID,
                "supersedes": ROOT_ID,
                "decided": "2026-08-22T12:01:00Z",
            },
        )
        connection.commit()

    index = PersistentIdentityIndex(migrated_engine)
    with pytest.raises(CorruptStoredDataError, match="stored identity resolution"):
        index.active_by_alias("gold", "ligand_17")
    with pytest.raises(CorruptStoredDataError, match="stored identity resolution"):
        index.catalog_by_state_hash("a" * 64)


def test_missing_predecessor_is_safe_in_active_and_catalog(
    migrated_engine: Engine,
) -> None:
    project = _project()
    batch = _batch(
        project.id,
        "d1d1d1d1-d1d1-41d1-81d1-d1d1d1d1d1d1",
        ImportStatus.COMPLETED,
    )
    missing_predecessor = "d2d2d2d2-d2d2-42d2-82d2-d2d2d2d2d2d2"
    successor_id = "d3d3d3d3-d3d3-43d3-83d3-d3d3d3d3d3d3"
    with UnitOfWork(migrated_engine) as uow:
        uow.projects.add(project)
        uow.import_batches.add(batch)
        uow.compounds.add(_compound())
        uow.molecular_states.add(_state(STATE_A_ID, "a" * 64))
        uow.aliases.add(_alias(batch.id))
    with migrated_engine.connect() as connection:
        connection.execute(text("PRAGMA foreign_keys=OFF"))
        connection.execute(text("PRAGMA ignore_check_constraints=ON"))
        connection.execute(text("DROP TRIGGER trg_identity_resolution_validate_insert"))
        connection.execute(
            text(
                "INSERT INTO identity_resolution "
                "(id,alias_id,decision,compound_id,molecular_state_id,"
                "supersedes_id,decided_at,actor_kind) VALUES "
                "(:id,:alias,'reassigned',:compound,:state,:supersedes,:decided,'system')"
            ),
            {
                "id": successor_id,
                "alias": ALIAS_ID,
                "compound": COMPOUND_ID,
                "state": STATE_A_ID,
                "supersedes": missing_predecessor,
                "decided": "2026-08-22T12:01:00Z",
            },
        )
        connection.commit()

    index = PersistentIdentityIndex(migrated_engine)
    with pytest.raises(CorruptStoredDataError, match="stored identity resolution"):
        index.active_by_alias("gold", "ligand_17")
    with pytest.raises(CorruptStoredDataError, match="stored identity resolution"):
        index.catalog_by_state_hash("a" * 64)


def test_cycle_in_resolution_chain_is_safe_in_active_and_catalog(
    migrated_engine: Engine,
) -> None:
    project = _project()
    batch = _batch(
        project.id,
        "d4d4d4d4-d4d4-44d4-84d4-d4d4d4d4d4d4",
        ImportStatus.COMPLETED,
    )
    first_id = "d5d5d5d5-d5d5-45d5-85d5-d5d5d5d5d5d5"
    second_id = "d6d6d6d6-d6d6-46d6-86d6-d6d6d6d6d6d6"
    with UnitOfWork(migrated_engine) as uow:
        uow.projects.add(project)
        uow.import_batches.add(batch)
        uow.compounds.add(_compound())
        uow.molecular_states.add(_state(STATE_A_ID, "a" * 64))
        uow.aliases.add(_alias(batch.id))
    with migrated_engine.connect() as connection:
        connection.execute(text("PRAGMA foreign_keys=OFF"))
        connection.execute(text("PRAGMA ignore_check_constraints=ON"))
        connection.execute(text("DROP TRIGGER trg_identity_resolution_validate_insert"))
        for row_id, predecessor in (
            (first_id, second_id),
            (second_id, first_id),
        ):
            connection.execute(
                text(
                    "INSERT INTO identity_resolution "
                    "(id,alias_id,decision,compound_id,molecular_state_id,"
                    "supersedes_id,decided_at,actor_kind) VALUES "
                    "(:id,:alias,'reassigned',:compound,:state,:supersedes,"
                    ":decided,'system')"
                ),
                {
                    "id": row_id,
                    "alias": ALIAS_ID,
                    "compound": COMPOUND_ID,
                    "state": STATE_A_ID,
                    "supersedes": predecessor,
                    "decided": "2026-08-22T12:01:00Z",
                },
            )
        connection.commit()

    index = PersistentIdentityIndex(migrated_engine)
    with pytest.raises(CorruptStoredDataError, match="stored identity resolution"):
        index.active_by_alias("gold", "ligand_17")
    with pytest.raises(CorruptStoredDataError, match="stored identity resolution"):
        index.catalog_by_state_hash("a" * 64)


def test_cross_alias_successor_is_safe_in_active_and_catalog(
    migrated_engine: Engine,
) -> None:
    project = _project()
    batch = _batch(
        project.id,
        "d7d7d7d7-d7d7-47d7-87d7-d7d7d7d7d7d7",
        ImportStatus.COMPLETED,
    )
    second_alias_id = "d8d8d8d8-d8d8-48d8-88d8-d8d8d8d8d8d8"
    successor_id = "d9d9d9d9-d9d9-49d9-89d9-d9d9d9d9d9d9"
    with UnitOfWork(migrated_engine) as uow:
        uow.projects.add(project)
        uow.import_batches.add(batch)
        uow.compounds.add(_compound())
        uow.molecular_states.add(_state(STATE_A_ID, "a" * 64))
        uow.aliases.add(_alias(batch.id))
        uow.aliases.add(
            Alias(
                id=second_alias_id,
                source_system="gold",
                source_value="cross-alias",
                import_batch_id=batch.id,
                created_at=NOW,
            )
        )
        uow.identity_resolutions.add(_resolution())
    with migrated_engine.connect() as connection:
        connection.execute(text("PRAGMA ignore_check_constraints=ON"))
        connection.execute(text("DROP TRIGGER trg_identity_resolution_validate_insert"))
        connection.execute(
            text(
                "INSERT INTO identity_resolution "
                "(id,alias_id,decision,compound_id,molecular_state_id,"
                "supersedes_id,decided_at,actor_kind) VALUES "
                "(:id,:alias,'reassigned',:compound,:state,:supersedes,:decided,'system')"
            ),
            {
                "id": successor_id,
                "alias": second_alias_id,
                "compound": COMPOUND_ID,
                "state": STATE_A_ID,
                "supersedes": ROOT_ID,
                "decided": "2026-08-22T12:01:00Z",
            },
        )
        connection.commit()

    index = PersistentIdentityIndex(migrated_engine)
    with pytest.raises(CorruptStoredDataError, match="stored identity resolution"):
        index.active_by_alias("gold", "ligand_17")
    with pytest.raises(CorruptStoredDataError, match="stored identity resolution"):
        index.catalog_by_state_hash("a" * 64)


def test_forked_successors_are_safe_in_active_and_catalog(
    migrated_engine: Engine,
) -> None:
    project = _project()
    batch = _batch(
        project.id,
        "e1e1e1e1-e1e1-41e1-81e1-e1e1e1e1e1e1",
        ImportStatus.COMPLETED,
    )
    first_successor = "e2e2e2e2-e2e2-42e2-82e2-e2e2e2e2e2e2"
    second_successor = "e3e3e3e3-e3e3-43e3-83e3-e3e3e3e3e3e3"
    with UnitOfWork(migrated_engine) as uow:
        uow.projects.add(project)
        uow.import_batches.add(batch)
        uow.compounds.add(_compound())
        uow.molecular_states.add(_state(STATE_A_ID, "a" * 64))
        uow.aliases.add(_alias(batch.id))
        uow.identity_resolutions.add(_resolution())
    with migrated_engine.connect() as connection:
        connection.execute(text("PRAGMA ignore_check_constraints=ON"))
        connection.execute(text("DROP TRIGGER trg_identity_resolution_validate_insert"))
        table_sql = connection.execute(
            text(
                "SELECT sql FROM sqlite_master "
                "WHERE type='table' AND name='identity_resolution'"
            )
        ).scalar_one()
        connection.execute(text("PRAGMA writable_schema=ON"))
        connection.execute(
            text(
                "UPDATE sqlite_master SET sql=:sql "
                "WHERE type='table' AND name='identity_resolution'"
            ),
            {
                "sql": table_sql.replace(
                    "CONSTRAINT uq_identity_resolution_supersedes "
                    "UNIQUE (supersedes_id), ",
                    "",
                )
            },
        )
        connection.execute(
            text(
                "DELETE FROM sqlite_master WHERE type='index' "
                "AND name='sqlite_autoindex_identity_resolution_2'"
            )
        )
        connection.execute(text("PRAGMA writable_schema=OFF"))
        connection.execute(text("PRAGMA schema_version=2147483000"))
        for successor_id in (first_successor, second_successor):
            connection.execute(
                text(
                    "INSERT INTO identity_resolution "
                    "(id,alias_id,decision,compound_id,molecular_state_id,"
                    "supersedes_id,decided_at,actor_kind) VALUES "
                    "(:id,:alias,'reassigned',:compound,:state,:supersedes,"
                    ":decided,'system')"
                ),
                {
                    "id": successor_id,
                    "alias": ALIAS_ID,
                    "compound": COMPOUND_ID,
                    "state": STATE_A_ID,
                    "supersedes": ROOT_ID,
                    "decided": "2026-08-22T12:01:00Z",
                },
            )
        connection.commit()

    index = PersistentIdentityIndex(migrated_engine)
    with pytest.raises(CorruptStoredDataError, match="stored identity resolution"):
        index.active_by_alias("gold", "ligand_17")
    with pytest.raises(CorruptStoredDataError, match="stored identity resolution"):
        index.catalog_by_state_hash("a" * 64)


def test_missing_compound_target_is_safe_in_active_projection(
    migrated_engine: Engine,
) -> None:
    project = _project()
    batch = _batch(
        project.id,
        "dededede-dede-4ded-8ded-dededededede",
        ImportStatus.COMPLETED,
    )
    alias_id = "d1d1d1d1-d1d1-41d1-81d1-d1d1d1d1d1d1"
    with UnitOfWork(migrated_engine) as uow:
        uow.projects.add(project)
        uow.import_batches.add(batch)
        uow.aliases.add(
            Alias(
                id=alias_id,
                source_system="gold",
                source_value="missing-compound",
                import_batch_id=batch.id,
                created_at=NOW,
            )
        )
    with migrated_engine.connect() as connection:
        connection.execute(text("PRAGMA foreign_keys=OFF"))
        connection.execute(text("PRAGMA ignore_check_constraints=ON"))
        connection.execute(text("DROP TRIGGER trg_identity_resolution_validate_insert"))
        connection.execute(
            text(
                "INSERT INTO identity_resolution "
                "(id,alias_id,decision,compound_id,molecular_state_id,"
                "decided_at,actor_kind) "
                "VALUES ('d2d2d2d2-d2d2-42d2-82d2-d2d2d2d2d2d2',:alias,'confirmed',"
                ":missing_compound,NULL,:decided,'system')"
            ),
            {
                "alias": alias_id,
                "missing_compound": MISSING_COMPOUND_ID,
                "decided": "2026-08-22T12:00:00Z",
            },
        )
        connection.commit()

    with pytest.raises(CorruptStoredDataError, match="stored identity resolution"):
        PersistentIdentityIndex(migrated_engine).active_by_alias(
            "gold", "missing-compound"
        )


def test_missing_state_target_is_safe_in_active_projection(
    migrated_engine: Engine,
) -> None:
    project = _project()
    batch = _batch(
        project.id,
        "d3d3d3d3-d3d3-43d3-83d3-d3d3d3d3d3d3",
        ImportStatus.COMPLETED,
    )
    alias_id = "d4d4d4d4-d4d4-44d4-84d4-d4d4d4d4d4d4"
    with UnitOfWork(migrated_engine) as uow:
        uow.projects.add(project)
        uow.import_batches.add(batch)
        uow.compounds.add(_compound())
        uow.aliases.add(
            Alias(
                id=alias_id,
                source_system="gold",
                source_value="missing-state",
                import_batch_id=batch.id,
                created_at=NOW,
            )
        )
    with migrated_engine.connect() as connection:
        connection.execute(text("PRAGMA foreign_keys=OFF"))
        connection.execute(text("PRAGMA ignore_check_constraints=ON"))
        connection.execute(text("DROP TRIGGER trg_identity_resolution_validate_insert"))
        connection.execute(
            text(
                "INSERT INTO identity_resolution "
                "(id,alias_id,decision,compound_id,molecular_state_id,"
                "decided_at,actor_kind) "
                "VALUES ('d5d5d5d5-d5d5-45d5-85d5-d5d5d5d5d5d5',:alias,'confirmed',"
                ":compound,:missing_state,:decided,'system')"
            ),
            {
                "alias": alias_id,
                "compound": COMPOUND_ID,
                "missing_state": MISSING_STATE_ID,
                "decided": "2026-08-22T12:00:00Z",
            },
        )
        connection.commit()

    with pytest.raises(CorruptStoredDataError, match="stored identity resolution"):
        PersistentIdentityIndex(migrated_engine).active_by_alias(
            "gold", "missing-state"
        )
    with pytest.raises(CorruptStoredDataError, match="stored identity resolution"):
        PersistentIdentityIndex(migrated_engine).catalog_by_parent_hash("a" * 64)


def test_ownership_mismatch_is_safe_in_active_projection(
    migrated_engine: Engine,
) -> None:
    project = _project()
    batch = _batch(
        project.id,
        "d6d6d6d6-d6d6-46d6-86d6-d6d6d6d6d6d6",
        ImportStatus.COMPLETED,
    )
    other_compound_id = "77777777-2222-4222-8222-222222222222"
    other_state_id = "88888888-3333-4333-8333-333333333333"
    alias_id = "d7d7d7d7-d7d7-47d7-87d7-d7d7d7d7d7d7"
    other_compound = _compound().model_copy(
        update={
            "id": other_compound_id,
            "structure_hash": "8" * 64,
            "inchikey": "VNWKTOKETHGBQD-UHFFFAOYSA-N",
        }
    )
    other_state = _state(other_state_id, "9" * 64).model_copy(
        update={"compound_id": other_compound_id}
    )
    with UnitOfWork(migrated_engine) as uow:
        uow.projects.add(project)
        uow.import_batches.add(batch)
        uow.compounds.add(_compound())
        uow.compounds.add(other_compound)
        uow.molecular_states.add(other_state)
        uow.aliases.add(
            Alias(
                id=alias_id,
                source_system="gold",
                source_value="ownership-mismatch",
                import_batch_id=batch.id,
                created_at=NOW,
            )
        )
    with migrated_engine.connect() as connection:
        connection.execute(text("PRAGMA foreign_keys=OFF"))
        connection.execute(text("PRAGMA ignore_check_constraints=ON"))
        connection.execute(text("DROP TRIGGER trg_identity_resolution_validate_insert"))
        connection.execute(
            text(
                "INSERT INTO identity_resolution "
                "(id,alias_id,decision,compound_id,molecular_state_id,"
                "decided_at,actor_kind) "
                "VALUES ('d8d8d8d8-d8d8-48d8-88d8-d8d8d8d8d8d8',:alias,'confirmed',"
                ":compound,:state,:decided,'system')"
            ),
            {
                "alias": alias_id,
                "compound": COMPOUND_ID,
                "state": other_state_id,
                "decided": "2026-08-22T12:00:00Z",
            },
        )
        connection.commit()

    with pytest.raises(CorruptStoredDataError, match="stored identity resolution"):
        PersistentIdentityIndex(migrated_engine).active_by_alias(
            "gold", "ownership-mismatch"
        )
    with pytest.raises(CorruptStoredDataError, match="stored identity resolution"):
        PersistentIdentityIndex(migrated_engine).catalog_by_state_hash("9" * 64)


def test_corrupt_batch_status_is_not_hidden_by_active_filter(
    migrated_engine: Engine,
) -> None:
    project = _project()
    batch_id = "f1f1f1f1-f1f1-41f1-81f1-f1f1f1f1f1f1"
    alias_id = "f2f2f2f2-f2f2-42f2-82f2-f2f2f2f2f2f2"
    resolution_id = "f3f3f3f3-f3f3-43f3-83f3-f3f3f3f3f3f3"
    with UnitOfWork(migrated_engine) as uow:
        uow.projects.add(project)
        uow.compounds.add(_compound())
        uow.molecular_states.add(_state(STATE_A_ID, "a" * 64))
    with migrated_engine.connect() as connection:
        connection.execute(text("PRAGMA ignore_check_constraints=ON"))
        connection.execute(
            text(
                "INSERT INTO import_batch "
                "(id,project_id,adapter_id,adapter_version,started_at,status,"
                "source_root,file_count) VALUES "
                "(:id,:project,'','1',:started,'completed','inputs',0)"
            ),
            {
                "id": batch_id,
                "project": PROJECT_ID,
                "started": "2026-08-22T12:00:00Z",
            },
        )
        connection.execute(
            text(
                "INSERT INTO alias "
                "(id,source_system,source_value,import_batch_id,created_at) "
                "VALUES (:id,'gold','corrupt-alias',:batch,:created)"
            ),
            {
                "id": alias_id,
                "batch": batch_id,
                "created": "2026-08-22T12:00:00Z",
            },
        )
        connection.execute(
            text(
                "INSERT INTO identity_resolution "
                "(id,alias_id,decision,compound_id,molecular_state_id,"
                "decided_at,actor_kind) VALUES "
                "(:id,:alias,'confirmed',:compound,:state,:decided,'system')"
            ),
            {
                "id": resolution_id,
                "alias": alias_id,
                "compound": COMPOUND_ID,
                "state": STATE_A_ID,
                "decided": "2026-08-22T12:00:00Z",
            },
        )
        connection.commit()

    with pytest.raises(CorruptStoredDataError, match="stored identity resolution"):
        PersistentIdentityIndex(migrated_engine).active_by_alias(
            "gold", "corrupt-alias"
        )
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
