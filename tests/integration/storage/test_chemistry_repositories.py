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
NEXT_ID = "55555555-5555-4555-8555-555555555555"
ALIAS_2_ID = "66666666-6666-4666-8666-666666666666"
ROOT_2_ID = "77777777-7777-4777-8777-777777777777"
STATE_2_ID = "88888888-8888-4888-8888-888888888888"
ALIAS_3_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
ROOT_3_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
RETRACT_3_ID = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
NEXT_2_ID = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"


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


def _seed_identity(engine: Engine) -> tuple[Project, ImportBatch, Alias, Compound]:
    project = _project()
    batch = _batch(project)
    compound = _compound()
    alias = _alias(batch.id)
    with UnitOfWork(engine) as uow:
        uow.projects.add(project)
        uow.import_batches.add(batch)
        uow.compounds.add(compound)
        uow.aliases.add(alias)
        uow.identity_resolutions.add(_resolution())
    return project, batch, alias, compound


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


def test_alias_natural_conflict_is_distinct_from_primary_key_conflict(
    migrated_engine: Engine,
) -> None:
    project = _project()
    batch = _batch(project)
    alias = _alias(batch.id)
    with UnitOfWork(migrated_engine) as uow:
        uow.projects.add(project)
        uow.import_batches.add(batch)
        uow.aliases.add(alias)
    natural_conflict = alias.model_copy(
        update={"id": "55555555-5555-4555-8555-555555555555"}
    )
    with pytest.raises(AliasConflictError), UnitOfWork(migrated_engine) as uow:
        uow.aliases.add(natural_conflict)
    primary_key_conflict = alias.model_copy(update={"source_value": "different"})
    with pytest.raises(DuplicateRecordError), UnitOfWork(migrated_engine) as uow:
        uow.aliases.add(primary_key_conflict)


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


def test_identity_repository_maps_second_successor_and_cross_alias_conflicts(
    migrated_engine: Engine,
) -> None:
    _, batch, alias, compound = _seed_identity(migrated_engine)
    with UnitOfWork(migrated_engine) as uow:
        uow.identity_resolutions.add(
            _resolution(
                resolution_id=NEXT_ID,
                decision=IdentityDecision.REASSIGNED,
                supersedes_id=ROOT_ID,
            )
        )
    with pytest.raises(IdentityResolutionConflictError) as raised, UnitOfWork(
        migrated_engine
    ) as uow:
        uow.identity_resolutions.add(
            _resolution(
                resolution_id=NEXT_2_ID,
                decision=IdentityDecision.REASSIGNED,
                supersedes_id=ROOT_ID,
            )
        )
    assert "sql" not in str(raised.value).lower()

    second_alias = alias.model_copy(update={"id": ALIAS_2_ID, "source_value": "456"})
    with UnitOfWork(migrated_engine) as uow:
        uow.aliases.add(second_alias)
        uow.identity_resolutions.add(
            _resolution(second_alias.id, resolution_id=ROOT_2_ID)
        )
    cross_alias = _resolution(
        alias.id,
        resolution_id="eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
        decision=IdentityDecision.REASSIGNED,
        supersedes_id=ROOT_2_ID,
    )
    with pytest.raises(IdentityResolutionConflictError), UnitOfWork(
        migrated_engine
    ) as uow:
        uow.identity_resolutions.add(cross_alias)
    del batch, compound


def test_identity_repository_maps_invalid_restore_and_repeated_retract(
    migrated_engine: Engine,
) -> None:
    _, batch, alias, compound = _seed_identity(migrated_engine)
    invalid_restore = IdentityResolution(
        id=NEXT_ID,
        alias_id=alias.id,
        decision=IdentityDecision.RESTORED,
        compound_id=compound.id,
        supersedes_id=ROOT_ID,
        decided_at=NOW,
        actor_kind=ActorKind.USER,
        actor_id="reviewer",
        rationale="reviewed",
    )
    with pytest.raises(IdentityResolutionConflictError), UnitOfWork(
        migrated_engine
    ) as uow:
        uow.identity_resolutions.add(invalid_restore)

    alias_3 = alias.model_copy(update={"id": ALIAS_3_ID, "source_value": "789"})
    with UnitOfWork(migrated_engine) as uow:
        uow.aliases.add(alias_3)
        uow.identity_resolutions.add(
            _resolution(alias_3.id, resolution_id=ROOT_3_ID)
        )
        uow.identity_resolutions.add(
            _resolution(
                alias_3.id,
                resolution_id=RETRACT_3_ID,
                decision=IdentityDecision.RETRACTED,
                compound_id=None,
                supersedes_id=ROOT_3_ID,
            )
        )
    repeated = _resolution(
        alias_3.id,
        resolution_id=NEXT_2_ID,
        decision=IdentityDecision.RETRACTED,
        compound_id=None,
        supersedes_id=RETRACT_3_ID,
    )
    with pytest.raises(IdentityResolutionConflictError), UnitOfWork(
        migrated_engine
    ) as uow:
        uow.identity_resolutions.add(repeated)
    del batch


def test_state_ownership_and_state_hash_conflicts_are_typed(
    migrated_engine: Engine,
) -> None:
    project, batch, alias, compound = _seed_identity(migrated_engine)
    second_compound = _compound(
        "99999999-9999-4999-8999-999999999999", digest="c" * 64
    )
    second_state = _state(second_compound.id).model_copy(update={"id": STATE_2_ID})
    with UnitOfWork(migrated_engine) as uow:
        uow.compounds.add(second_compound)
        uow.molecular_states.add(second_state)
    bad_ownership = IdentityResolution(
        id=NEXT_ID,
        alias_id=alias.id,
        decision=IdentityDecision.REASSIGNED,
        compound_id=compound.id,
        molecular_state_id=second_state.id,
        supersedes_id=ROOT_ID,
        decided_at=NOW,
        actor_kind=ActorKind.SYSTEM,
    )
    with pytest.raises(IdentityResolutionConflictError), UnitOfWork(
        migrated_engine
    ) as uow:
        uow.identity_resolutions.add(bad_ownership)
    with pytest.raises(DuplicateRecordError), UnitOfWork(migrated_engine) as uow:
        uow.molecular_states.add(
            _state(compound.id).model_copy(update={"id": STATE_2_ID})
        )
    del project, batch


def test_populated_provenance_and_deterministic_identity_lists(
    migrated_engine: Engine,
) -> None:
    project = _project()
    batch = _batch(project)
    compound = _compound().model_copy(
        update={
            "inchikey": "LFQSCWFLJHTTHZ-UHFFFAOYSA-N",
            "inchi_version": "1.0.0",
        }
    )
    state = _state().model_copy(
        update={
            "state_inchikey": "LFQSCWFLJHTTHZ-UHFFFAOYSA-N",
            "inchi_version": "1.0.0",
        }
    )
    alias = _alias(batch.id)
    alias_2 = alias.model_copy(
        update={"id": ALIAS_2_ID, "source_value": "456"}
    )
    with UnitOfWork(migrated_engine) as uow:
        uow.projects.add(project)
        uow.import_batches.add(batch)
        uow.compounds.add(compound)
        uow.molecular_states.add(state)
        uow.aliases.add(alias_2)
        uow.aliases.add(alias)
        uow.identity_resolutions.add(_resolution(alias_2.id, resolution_id=ROOT_2_ID))
        uow.identity_resolutions.add(_resolution(alias.id))
        assert uow.aliases.list_by_batch(batch.id) == (alias, alias_2)
        assert uow.identity_resolutions.list_by_alias(alias.id) == (_resolution(),)
    with UnitOfWork(migrated_engine) as uow:
        assert uow.compounds.get(compound.id) == compound
        assert uow.molecular_states.get(state.id) == state


def test_corrupt_state_alias_and_resolution_rows_are_safe(
    migrated_engine: Engine,
) -> None:
    _project_row, batch, _alias_row, compound = _seed_identity(migrated_engine)
    with migrated_engine.connect() as connection:
        connection.execute(text("PRAGMA ignore_check_constraints=ON"))
        connection.execute(
            text(
                "INSERT INTO molecular_state "
                "(id,compound_id,state_smiles,formal_charge,stereochemistry_signature,"
                "protonation_signature,tautomer_signature,state_hash,"
                "chemistry_policy_id,rdkit_version) VALUES "
                "('bad-state',:compound,'C',0,'none','neutral','canonical',"
                "'bad','v1','rdkit')"
            ),
            {"compound": compound.id},
        )
        connection.execute(
            text(
                "INSERT INTO alias "
                "(id,source_system,source_value,import_batch_id,created_at) "
                "VALUES ('bad-alias','BAD','x',:batch,:at)"
            ),
            {"batch": batch.id, "at": NOW.isoformat().replace("+00:00", "Z")},
        )
        connection.execute(
            text(
                "INSERT INTO identity_resolution "
                "(id,alias_id,decision,compound_id,decided_at,actor_kind) "
                "VALUES ('bad-resolution',:alias,'confirmed',:compound,:at,'robot')"
            ),
            {
                "alias": "bad-alias",
                "compound": compound.id,
                "at": NOW.isoformat().replace("+00:00", "Z"),
            },
        )
        connection.commit()
    with (
        pytest.raises(CorruptStoredDataError, match="stored molecular state"),
        UnitOfWork(migrated_engine) as uow,
    ):
        uow.molecular_states.get("bad-state")
    with (
        pytest.raises(CorruptStoredDataError, match="stored alias"),
        UnitOfWork(migrated_engine) as uow,
    ):
        uow.aliases.get("bad-alias")
    with (
        pytest.raises(CorruptStoredDataError, match="stored identity resolution"),
        UnitOfWork(migrated_engine) as uow,
    ):
        uow.identity_resolutions.get("bad-resolution")
