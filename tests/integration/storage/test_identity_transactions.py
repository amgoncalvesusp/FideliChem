from __future__ import annotations

from contextlib import suppress
from datetime import UTC, datetime
from threading import Barrier, Thread

import pytest
from sqlalchemy import Engine, text

from fidelichem.domain.chemistry import (
    Alias,
    Compound,
    IdentityDecision,
    IdentityResolution,
)
from fidelichem.domain.errors import AliasConflictError, IdentityResolutionConflictError
from fidelichem.domain.models import ActorKind, ImportBatch, Project
from fidelichem.storage.chemistry_repositories import (
    AliasRepository,
    IdentityResolutionRepository,
)
from fidelichem.storage.repositories import ForeignKeyViolationError, StorageWriteError
from fidelichem.storage.session import (
    UnitOfWork,
    UnitOfWorkError,
    create_session_factory,
)

NOW = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)
ALIAS_ID = "11111111-1111-4111-8111-111111111111"
ROOT_ID = "22222222-2222-4222-8222-222222222222"
RACE_A = "33333333-3333-4333-8333-333333333333"
RACE_B = "44444444-4444-4444-8444-444444444444"


def _project() -> Project:
    return Project(name="Project", created_at=NOW, updated_at=NOW)


def _batch(project_id: str) -> ImportBatch:
    return ImportBatch(
        project_id=project_id,
        adapter_id="adapter",
        adapter_version="1",
        started_at=NOW,
        source_root="inputs",
    )


def _compound() -> Compound:
    return Compound(
        id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        canonical_smiles="CCO",
        isomeric_smiles="CCO",
        formula="C2H6O",
        molecular_weight=46.069,
        structure_hash="a" * 64,
        chemistry_policy_id="fidelichem.rdkit-identity.v1",
        rdkit_version="2026.3.4",
        created_at=NOW,
    )


def _alias(batch_id: str, alias_id: str = ALIAS_ID) -> Alias:
    return Alias(
        id=alias_id,
        source_system="pubchem",
        source_value="123",
        import_batch_id=batch_id,
        created_at=NOW,
    )


def _root(alias_id: str = ALIAS_ID, resolution_id: str = ROOT_ID) -> IdentityResolution:
    return IdentityResolution(
        id=resolution_id,
        alias_id=alias_id,
        decision=IdentityDecision.CONFIRMED,
        compound_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        decided_at=NOW,
        actor_kind=ActorKind.SYSTEM,
    )


def _successor(
    alias_id: str, predecessor_id: str, resolution_id: str
) -> IdentityResolution:
    return IdentityResolution(
        id=resolution_id,
        alias_id=alias_id,
        decision=IdentityDecision.REASSIGNED,
        compound_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        supersedes_id=predecessor_id,
        decided_at=NOW,
        actor_kind=ActorKind.SYSTEM,
    )


def _run_repository_race(
    migrated_engine: Engine,
    values: tuple[object, object],
    repository_type: type,
    expected_error: type[Exception],
) -> list[str]:
    barrier = Barrier(2)
    results: list[str] = []
    factory = create_session_factory(migrated_engine)

    def worker(value: object) -> None:
        try:
            with factory() as session:
                barrier.wait()
                try:
                    repository_type(session).add(value)
                    session.commit()
                    results.append("winner")
                except expected_error:
                    results.append("conflict")
                except StorageWriteError:
                    session.rollback()
                    with factory() as retry_session, pytest.raises(expected_error):
                        repository_type(retry_session).add(value)
                    results.append("conflict")
        except BaseException as error:  # pragma: no cover - surfaced below
            results.append(type(error).__name__)

    first = Thread(target=worker, args=(values[0],))
    second = Thread(target=worker, args=(values[1],))
    first.start()
    second.start()
    first.join(timeout=10)
    second.join(timeout=10)
    assert not first.is_alive() and not second.is_alive()
    return results


def test_identity_uow_rolls_back_prior_chemistry_writes_after_fk_failure(
    migrated_engine: Engine,
) -> None:
    factory = create_session_factory(migrated_engine)
    with pytest.raises(ForeignKeyViolationError), UnitOfWork(factory) as uow:
        uow.compounds.add(_compound())
        uow.import_batches.add(_batch("99999999-9999-4999-8999-999999999999"))

    with factory() as session:
        assert session.execute(text("SELECT count(*) FROM compound")).scalar_one() == 0


def test_identity_uow_repositories_fail_closed_after_swallowed_conflict(
    migrated_engine: Engine,
) -> None:
    with pytest.raises(UnitOfWorkError, match="failed"), UnitOfWork(
        migrated_engine
    ) as uow:
        project = _project()
        uow.projects.add(project)
        uow.compounds.add(_compound())
        with suppress(ForeignKeyViolationError):
            uow.import_batches.add(_batch("99999999-9999-4999-8999-999999999999"))
        with pytest.raises(UnitOfWorkError, match="failed"):
            uow.compounds.get("99999999-9999-4999-8999-999999999999")


def test_chemistry_repository_reference_is_inactive_after_uow_exit(
    migrated_engine: Engine,
) -> None:
    with UnitOfWork(migrated_engine) as uow:
        compounds = uow.compounds
    with pytest.raises(UnitOfWorkError, match="inactive"):
        compounds.get("99999999-9999-4999-8999-999999999999")


def test_two_session_alias_root_successor_races_have_one_typed_loser(
    migrated_engine: Engine,
) -> None:
    project = _project()
    batch = _batch(project.id)
    with UnitOfWork(migrated_engine) as uow:
        uow.projects.add(project)
        uow.import_batches.add(batch)
        uow.compounds.add(_compound())

    alias_results = _run_repository_race(
        migrated_engine,
        (_alias(batch.id, RACE_A), _alias(batch.id, RACE_B)),
        AliasRepository,
        AliasConflictError,
    )
    assert sorted(alias_results) == ["conflict", "winner"]
    with migrated_engine.connect() as connection:
        alias_id = connection.scalar(
            text(
                "SELECT id FROM alias WHERE import_batch_id=:batch "
                "AND source_system='pubchem' AND source_value='123'"
            ),
            {"batch": batch.id},
        )
        assert connection.scalar(
            text(
                "SELECT count(*) FROM alias WHERE import_batch_id=:batch "
                "AND source_system='pubchem' AND source_value='123'"
            ),
            {"batch": batch.id},
        ) == 1

    root_results = _run_repository_race(
        migrated_engine,
        (_root(alias_id, RACE_A), _root(alias_id, RACE_B)),
        IdentityResolutionRepository,
        IdentityResolutionConflictError,
    )
    assert sorted(root_results) == ["conflict", "winner"]
    with migrated_engine.connect() as connection:
        root_id = connection.scalar(
            text(
                "SELECT id FROM identity_resolution WHERE alias_id=:alias "
                "AND supersedes_id IS NULL"
            ),
            {"alias": alias_id},
        )
        assert connection.scalar(
            text(
                "SELECT count(*) FROM identity_resolution WHERE alias_id=:alias"
            ),
            {"alias": alias_id},
        ) == 1


    successor_results = _run_repository_race(
        migrated_engine,
        (
            _successor(alias_id, root_id, "55555555-5555-4555-8555-555555555555"),
            _successor(alias_id, root_id, "66666666-6666-4666-8666-666666666666"),
        ),
        IdentityResolutionRepository,
        IdentityResolutionConflictError,
    )
    assert sorted(successor_results) == ["conflict", "winner"]
    with migrated_engine.connect() as connection:
        assert connection.scalar(
            text(
                "SELECT count(*) FROM identity_resolution "
                "WHERE supersedes_id=:root"
            ),
            {"root": root_id},
        ) == 1


def test_caller_owned_identity_failure_recovers_after_explicit_rollback(
    migrated_engine: Engine,
) -> None:
    project = _project()
    batch = _batch(project.id)
    alias = _alias(batch.id, RACE_A)
    with UnitOfWork(migrated_engine) as uow:
        uow.projects.add(project)
        uow.import_batches.add(batch)
    factory = create_session_factory(migrated_engine)
    with factory() as session:
        repository = AliasRepository(session)
        repository.add(alias)
        session.commit()
        with pytest.raises(AliasConflictError):
            repository.add(alias.model_copy(update={"id": RACE_B}))
        with pytest.raises(UnitOfWorkError, match="failed"):
            repository.get(alias.id)
        session.rollback()
        recovered = AliasRepository(session)
        assert recovered.get(alias.id) == alias
        recovered.add(alias.model_copy(update={"id": ROOT_ID, "source_value": "456"}))
        session.commit()


def test_locked_alias_flush_fails_closed_then_retries_as_typed_conflict(
    migrated_engine: Engine,
) -> None:
    project = _project()
    batch = _batch(project.id)
    with UnitOfWork(migrated_engine) as uow:
        uow.projects.add(project)
        uow.import_batches.add(batch)
    alias = _alias(batch.id, RACE_A)
    factory = create_session_factory(migrated_engine)
    with factory() as winner, factory() as loser:
        AliasRepository(winner).add(alias)
        loser.connection().exec_driver_sql("PRAGMA busy_timeout=0")
        repository = AliasRepository(loser)
        with pytest.raises(StorageWriteError) as raised:
            repository.add(alias.model_copy(update={"id": RACE_B}))
        assert raised.value.__cause__ is None
        assert "sql" not in str(raised.value).lower()
        with pytest.raises(UnitOfWorkError, match="failed"):
            repository.get(alias.id)
        winner.commit()
        loser.rollback()
        with pytest.raises(AliasConflictError) as conflict:
            AliasRepository(loser).add(alias.model_copy(update={"id": RACE_B}))
        assert str(conflict.value) == "identity alias conflicts with an existing record"
        assert conflict.value.__cause__ is None
        loser.rollback()
    with migrated_engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM alias")) == 1


def test_locked_resolution_flush_fails_closed_then_retries_as_typed_conflict(
    migrated_engine: Engine,
) -> None:
    project = _project()
    batch = _batch(project.id)
    alias = _alias(batch.id, RACE_A)
    with UnitOfWork(migrated_engine) as uow:
        uow.projects.add(project)
        uow.import_batches.add(batch)
        uow.compounds.add(_compound())
        uow.aliases.add(alias)
    factory = create_session_factory(migrated_engine)
    with factory() as winner, factory() as loser:
        IdentityResolutionRepository(winner).add(_root(alias.id, RACE_A))
        loser.connection().exec_driver_sql("PRAGMA busy_timeout=0")
        repository = IdentityResolutionRepository(loser)
        with pytest.raises(StorageWriteError) as raised:
            repository.add(_root(alias.id, RACE_B))
        assert raised.value.__cause__ is None
        assert "sql" not in str(raised.value).lower()
        winner.commit()
        loser.rollback()
        with pytest.raises(IdentityResolutionConflictError) as conflict:
            IdentityResolutionRepository(loser).add(_root(alias.id, RACE_B))
        assert (
            str(conflict.value)
            == "identity resolution conflicts with the existing chain"
        )
        assert conflict.value.__cause__ is None
        loser.rollback()
    with migrated_engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM identity_resolution")) == 1
