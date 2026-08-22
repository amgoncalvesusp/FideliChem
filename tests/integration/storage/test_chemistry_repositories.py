from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine, text

from fidelichem.domain.chemistry import (
    Alias,
    Compound,
    IdentityDecision,
    IdentityResolution,
    MolecularState,
)
from fidelichem.domain.errors import AliasConflictError, IdentityResolutionConflictError
from fidelichem.domain.models import ActorKind, ImportBatch, Project
from fidelichem.storage.chemistry_repositories import (
    CompoundRepository,
)
from fidelichem.storage.repositories import (
    CorruptStoredDataError,
    DuplicateRecordError,
    ForeignKeyViolationError,
)
from fidelichem.storage.session import (
    UnitOfWork,
    UnitOfWorkError,
    create_session_factory,
)

NOW = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)
COMPOUND_ID = "11111111-1111-4111-8111-111111111111"
STATE_ID = "22222222-2222-4222-8222-222222222222"
ALIAS_ID = "33333333-3333-4333-8333-333333333333"
ROOT_ID = "44444444-4444-4444-8444-444444444444"


def _project() -> Project:
    return Project(name="Project", created_at=NOW, updated_at=NOW)


def _batch(project: Project) -> ImportBatch:
    return ImportBatch(
        project_id=project.id,
        adapter_id="adapter",
        adapter_version="1",
        started_at=NOW,
        source_root="inputs",
    )


def _compound(compound_id: str = COMPOUND_ID, digest: str = "a" * 64) -> Compound:
    return Compound(
        id=compound_id,
        canonical_smiles="CCO",
        isomeric_smiles="CCO",
        formula="C2H6O",
        molecular_weight=46.069,
        structure_hash=digest,
        chemistry_policy_id="fidelichem.rdkit-identity.v1",
        rdkit_version="2026.3.4",
        inchikey=None,
        inchi_version=None,
        created_at=NOW,
    )


def _state(compound_id: str = COMPOUND_ID) -> MolecularState:
    return MolecularState(
        id=STATE_ID,
        compound_id=compound_id,
        state_smiles="CCO",
        state_inchikey=None,
        formal_charge=0,
        stereochemistry_signature="none",
        protonation_signature="neutral",
        tautomer_signature="canonical",
        state_hash="b" * 64,
        chemistry_policy_id="fidelichem.rdkit-identity.v1",
        rdkit_version="2026.3.4",
        inchi_version=None,
        preparation_ph=None,
    )


def _alias(batch_id: str) -> Alias:
    return Alias(
        id=ALIAS_ID,
        source_system="pubchem",
        source_value="123",
        import_batch_id=batch_id,
        created_at=NOW,
    )


def _resolution(
    alias_id: str = ALIAS_ID,
    *,
    resolution_id: str = ROOT_ID,
    decision: IdentityDecision = IdentityDecision.CONFIRMED,
    compound_id: str | None = COMPOUND_ID,
    supersedes_id: str | None = None,
) -> IdentityResolution:
    return IdentityResolution(
        id=resolution_id,
        alias_id=alias_id,
        decision=decision,
        compound_id=compound_id,
        supersedes_id=supersedes_id,
        decided_at=NOW,
        actor_kind=ActorKind.SYSTEM,
    )


def test_chemistry_rows_round_trip_after_reopen_and_order_lists(
    migrated_engine: Engine,
) -> None:
    project = _project()
    batch = _batch(project)
    compound = _compound()
    state = _state()
    alias = _alias(batch.id)
    root = _resolution()
    with UnitOfWork(migrated_engine) as uow:
        uow.projects.add(project)
        uow.import_batches.add(batch)
        assert uow.compounds.add(compound) == compound
        assert uow.molecular_states.add(state) == state
        assert uow.aliases.add(alias) == alias
        assert uow.identity_resolutions.add(root) == root

    with UnitOfWork(migrated_engine) as uow:
        assert uow.compounds.get(compound.id) == compound
        assert uow.molecular_states.get(state.id) == state
        assert uow.aliases.get(alias.id) == alias
        assert uow.identity_resolutions.get(root.id) == root
        assert uow.identity_resolutions.list_by_alias(alias.id) == (root,)


def test_chemistry_repositories_return_none_for_missing_rows(
    migrated_engine: Engine,
) -> None:
    with UnitOfWork(migrated_engine) as uow:
        missing = "99999999-9999-4999-8999-999999999999"
        assert uow.compounds.get(missing) is None
        assert uow.molecular_states.get(missing) is None
        assert uow.aliases.get(missing) is None
        assert uow.identity_resolutions.get(missing) is None


def test_duplicate_hash_and_alias_are_typed_conflicts(
    migrated_engine: Engine,
) -> None:
    project = _project()
    batch = _batch(project)
    with UnitOfWork(migrated_engine) as uow:
        uow.projects.add(project)
        uow.import_batches.add(batch)
        uow.compounds.add(_compound())
        uow.aliases.add(_alias(batch.id))
    with pytest.raises(AliasConflictError), UnitOfWork(migrated_engine) as uow:
        uow.aliases.add(_alias(batch.id))
    with pytest.raises(DuplicateRecordError), UnitOfWork(migrated_engine) as uow:
        uow.compounds.add(_compound("55555555-5555-4555-8555-555555555555"))


def test_resolution_chain_conflicts_are_typed(migrated_engine: Engine) -> None:
    project = _project()
    batch = _batch(project)
    with pytest.raises(UnitOfWorkError, match="failed"), UnitOfWork(
        migrated_engine
    ) as uow:
        uow.projects.add(project)
        uow.import_batches.add(batch)
        uow.compounds.add(_compound())
        uow.aliases.add(_alias(batch.id))
        uow.identity_resolutions.add(_resolution())
        with pytest.raises(IdentityResolutionConflictError):
            uow.identity_resolutions.add(
                _resolution(
                    "33333333-3333-4333-8333-333333333333",
                    resolution_id="66666666-6666-4666-8666-666666666666",
                )
            )


def test_caller_owned_session_never_commits(migrated_engine: Engine) -> None:
    factory = create_session_factory(migrated_engine)
    with factory() as session:
        CompoundRepository(session).add(_compound())
        with migrated_engine.connect() as connection:
            assert (
                connection.exec_driver_sql("SELECT count(*) FROM compound").scalar()
                == 0
            )
        session.rollback()


def test_chemistry_foreign_keys_are_typed(migrated_engine: Engine) -> None:
    with pytest.raises(ForeignKeyViolationError), UnitOfWork(migrated_engine) as uow:
        uow.molecular_states.add(_state("99999999-9999-4999-8999-999999999999"))
    with pytest.raises(ForeignKeyViolationError), UnitOfWork(migrated_engine) as uow:
        uow.aliases.add(_alias("99999999-9999-4999-8999-999999999999"))


def test_corrupt_chemistry_rows_map_to_safe_errors(migrated_engine: Engine) -> None:
    with migrated_engine.connect() as connection:
        connection.execute(text("PRAGMA ignore_check_constraints=ON"))
        connection.execute(
            text(
                "INSERT INTO compound "
                "(id,canonical_smiles,isomeric_smiles,formula,molecular_weight,"
                "structure_hash,chemistry_policy_id,rdkit_version,created_at) "
                "VALUES ('not-a-uuid','C','C','CH4',1,'bad','v1','rdkit','bad')"
            )
        )
        connection.commit()
    with (
        pytest.raises(CorruptStoredDataError, match="stored compound"),
        UnitOfWork(migrated_engine) as uow,
    ):
        uow.compounds.get("not-a-uuid")
