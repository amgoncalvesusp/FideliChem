from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import Engine

from fidelichem.domain.chemistry import (
    Alias,
    CanonicalizationResult,
    Compound,
    IdentityActor,
    IdentityClaim,
    IdentityDecision,
    IdentityResolution,
    IdentitySelection,
    MolecularState,
    SelectionMode,
)
from fidelichem.domain.errors import IdentityResolutionConflictError
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
from fidelichem.storage.repositories import RecordNotFoundError
from fidelichem.storage.runner import upgrade_database
from fidelichem.storage.session import UnitOfWork

NOW = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)
PROJECT_ID = "11111111-1111-4111-8111-111111111111"
BATCH_ID = "22222222-2222-4222-8222-222222222222"
COMPOUND_ID = "33333333-3333-4333-8333-333333333333"
STATE_ID = "44444444-4444-4444-8444-444444444444"
ALIAS_ID = "55555555-5555-4555-8555-555555555555"
RESOLUTION_ID = "66666666-6666-4666-8666-666666666666"
INCHI = "LFQSCWFLJHTTHZ-UHFFFAOYSA-N"


@pytest.fixture
def migrated_engine(tmp_path: Path) -> Iterator[Engine]:
    engine = create_sqlite_engine(tmp_path / "project.fidelichem.sqlite")
    upgrade_database(engine)
    try:
        yield engine
    finally:
        engine.dispose()


def _project() -> Project:
    return Project(id=PROJECT_ID, name="Identity", created_at=NOW, updated_at=NOW)


def _batch() -> ImportBatch:
    return ImportBatch(
        id=BATCH_ID,
        project_id=PROJECT_ID,
        adapter_id="adapter",
        adapter_version="1",
        started_at=NOW,
        completed_at=NOW,
        status=ImportStatus.COMPLETED,
        source_root="inputs",
    )


def _result(
    *,
    compound_id: str = COMPOUND_ID,
    state_id: str = STATE_ID,
    structure_hash: str = "b" * 64,
    state_hash: str = "a" * 64,
    source_smiles: str = "CCO",
) -> CanonicalizationResult:
    compound = Compound(
        id=compound_id,
        canonical_smiles="CCO",
        isomeric_smiles="CCO",
        inchikey=INCHI,
        formula="C2H6O",
        molecular_weight=46.069,
        structure_hash=structure_hash,
        chemistry_policy_id="fidelichem.rdkit-identity.v1",
        rdkit_version="2026.3.4",
        inchi_version="1.0.0",
        created_at=NOW,
    )
    state = MolecularState(
        id=state_id,
        compound_id=compound_id,
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
        source_smiles=source_smiles,
        compound=compound,
        molecular_state=state,
        chemistry_policy_id="fidelichem.rdkit-identity.v1",
    )


def _claim(
    *,
    batch_id: str | None = BATCH_ID,
    source_system: str | None = "gold",
    source_value: str | None = "ligand-1",
    smiles: str | None = "CCO",
) -> IdentityClaim:
    return IdentityClaim(
        smiles=smiles,
        source_system=source_system,
        source_value=source_value,
        import_batch_id=batch_id,
    )


def _actor(kind: ActorKind = ActorKind.SYSTEM) -> IdentityActor:
    return IdentityActor(
        kind=kind,
        actor_id=None if kind is ActorKind.SYSTEM else "reviewer",
        rationale=None if kind is ActorKind.SYSTEM else "confirmed by review",
    )


def _report(
    kind: ResolutionKind = ResolutionKind.NEW_COMPOUND,
    *,
    candidate: ResolutionCandidate | None = None,
    dormant: bool = False,
) -> ResolutionReport:
    return ResolutionReport(
        kind=kind,
        reason={
            ResolutionKind.NEW_COMPOUND: ResolutionReason.NEW_COMPOUND,
            ResolutionKind.EXACT_STATE: ResolutionReason.EXACT_STATE,
            ResolutionKind.NEW_STATE: ResolutionReason.PARENT_MATCH,
            ResolutionKind.ALIAS_ONLY: ResolutionReason.ALIAS_ONLY,
            ResolutionKind.AMBIGUOUS: ResolutionReason.AMBIGUOUS_ALIAS,
            ResolutionKind.CONFLICT: ResolutionReason.CONFLICTING_EVIDENCE,
            ResolutionKind.UNRESOLVED: ResolutionReason.UNRESOLVED,
        }[kind],
        candidates=() if candidate is None else (candidate,),
        catalog_action={
            ResolutionKind.NEW_COMPOUND: CatalogAction.CREATE_COMPOUND,
            ResolutionKind.NEW_STATE: CatalogAction.REUSE_COMPOUND,
            ResolutionKind.EXACT_STATE: CatalogAction.REUSE_STATE,
        }.get(kind, CatalogAction.NONE),
        catalog_match_dormant=dormant,
    )


def _service(
    engine: Engine,
    *,
    failpoint: Callable[[str], None] | None = None,
    factory_calls: list[int] | None = None,
    index_calls: list[int] | None = None,
) -> IdentityService:
    def make_uow() -> UnitOfWork:
        if factory_calls is not None:
            factory_calls.append(1)
        return UnitOfWork(engine)

    def make_index() -> PersistentIdentityIndex:
        if index_calls is not None:
            index_calls.append(1)
        return PersistentIdentityIndex(engine)

    return IdentityService(
        uow_factory=make_uow,
        index_factory=make_index,
        clock=lambda: NOW,
        failpoint=failpoint,
    )


def _seed_project_batch(engine: Engine) -> None:
    with UnitOfWork(engine) as uow:
        uow.projects.add(_project())
        uow.import_batches.add(_batch())


class _InterposingIndex:
    def __init__(self, delegate: PersistentIdentityIndex, mutate: Callable[[], None]):
        self._delegate = delegate
        self._mutate = mutate
        self._mutated = False

    def catalog_by_state_hash(self, state_hash: str):
        return self._delegate.catalog_by_state_hash(state_hash)

    def catalog_by_parent_hash(self, parent_hash: str):
        return self._delegate.catalog_by_parent_hash(parent_hash)

    def active_by_alias(self, source_system: str, source_value: str):
        return self._delegate.active_by_alias(source_system, source_value)

    def catalog_by_generated_inchikey(self, inchikey: str):
        values = self._delegate.catalog_by_generated_inchikey(inchikey)
        if not self._mutated:
            self._mutated = True
            self._mutate()
        return values


def _interposed_service(engine: Engine, mutate: Callable[[], None]) -> IdentityService:
    calls = 0

    def make_index():
        nonlocal calls
        calls += 1
        index = PersistentIdentityIndex(engine)
        return _InterposingIndex(index, mutate) if calls == 1 else index

    return IdentityService(
        uow_factory=lambda: UnitOfWork(engine),
        index_factory=make_index,
        clock=lambda: NOW,
    )


def _insert_interposed_parent(engine: Engine) -> None:
    with UnitOfWork(engine) as uow:
        uow.compounds.add(_result().compound)


def _insert_interposed_exact(engine: Engine) -> None:
    with UnitOfWork(engine) as uow:
        result = _result()
        uow.compounds.add(result.compound)
        uow.molecular_states.add(result.molecular_state)


def _insert_interposed_alias_conflict(engine: Engine) -> None:
    result = _result()
    other = _result(
        compound_id="77777777-7777-4777-8777-777777777777",
        state_id="88888888-8888-4888-8888-888888888888",
        structure_hash="c" * 64,
        state_hash="d" * 64,
    )
    with UnitOfWork(engine) as uow:
        uow.compounds.add(result.compound)
        uow.compounds.add(other.compound)
        prior_batch = _batch().model_copy(
            update={"id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"}
        )
        uow.import_batches.add(prior_batch)
        alias = uow.aliases.add(
            Alias(
                source_system="gold",
                source_value="ligand-1",
                import_batch_id=prior_batch.id,
                created_at=NOW,
            )
        )
        uow.identity_resolutions.add(
            IdentityResolution(
                alias_id=alias.id,
                decision=IdentityDecision.CONFIRMED,
                compound_id=other.compound.id,
                decided_at=NOW,
                actor_kind=ActorKind.SYSTEM,
            )
        )


def test_confirm_new_compound_persists_atomic_identity_and_audit(
    migrated_engine: Engine,
) -> None:
    _seed_project_batch(migrated_engine)
    result = _result()
    service = _service(migrated_engine)

    resolution = service.confirm_claim(
        result,
        _claim(),
        _report(),
        IdentitySelection(mode=SelectionMode.NEW_COMPOUND),
        _actor(),
    )

    assert resolution.decision is IdentityDecision.CONFIRMED
    with UnitOfWork(migrated_engine) as uow:
        assert uow.compounds.get(COMPOUND_ID) is not None
        assert uow.molecular_states.get(STATE_ID) is not None
        alias = uow.aliases.list_by_batch(BATCH_ID)
        assert len(alias) == 1
        decisions = uow.identity_resolutions.list_by_alias(alias[0].id)
        assert len(decisions) == 1
        events = uow.audit_events.list_by_batch(BATCH_ID)
        assert len(events) == 1
        payload = json.loads(events[0].new_value_json or "{}")
        assert payload["policy_id"] == result.chemistry_policy_id
        assert payload["state_hash"] == result.molecular_state.state_hash
        assert payload["structure_hash"] == result.compound.structure_hash
        assert payload["report_kind"] == ResolutionKind.NEW_COMPOUND.value
        assert payload["catalog_action"] == CatalogAction.CREATE_COMPOUND.value
        assert payload["actor_kind"] == ActorKind.SYSTEM.value


def test_confirm_rejects_stale_report_before_opening_uow_and_calls_live_index(
    migrated_engine: Engine,
) -> None:
    _seed_project_batch(migrated_engine)
    service = _service(migrated_engine)
    service.confirm_claim(
        _result(),
        _claim(),
        _report(),
        IdentitySelection(mode=SelectionMode.NEW_COMPOUND),
        _actor(),
    )
    uow_calls: list[int] = []
    index_calls: list[int] = []
    stale = _service(migrated_engine, factory_calls=uow_calls, index_calls=index_calls)
    with pytest.raises(ValueError, match="stale"):
        stale.confirm_claim(
            _result(),
            _claim(source_value="ligand-2"),
            _report(),
            IdentitySelection(mode=SelectionMode.NEW_COMPOUND),
            _actor(),
        )
    assert index_calls == [1]
    assert uow_calls == []


def test_confirm_rejects_stale_new_state_when_live_state_is_exact(
    migrated_engine: Engine,
) -> None:
    _seed_project_batch(migrated_engine)
    service = _service(migrated_engine)
    service.confirm_claim(
        _result(),
        _claim(),
        _report(),
        IdentitySelection(mode=SelectionMode.NEW_COMPOUND),
        _actor(),
    )
    with pytest.raises(ValueError, match="stale"):
        service.confirm_claim(
            _result(),
            _claim(source_value="ligand-2"),
            _report(
                ResolutionKind.NEW_STATE,
                candidate=ResolutionCandidate(compound_id=COMPOUND_ID),
            ),
            IdentitySelection(
                mode=SelectionMode.EXISTING_TARGET, compound_id=COMPOUND_ID
            ),
            _actor(),
        )


@pytest.mark.parametrize(
    ("mutator", "label"),
    (
        (_insert_interposed_parent, "parent"),
        (_insert_interposed_exact, "exact"),
        (_insert_interposed_alias_conflict, "alias"),
    ),
)
def test_confirm_revalidates_after_interposed_write_without_extra_rows(
    migrated_engine: Engine,
    mutator: Callable[[Engine], None],
    label: str,
) -> None:
    _seed_project_batch(migrated_engine)
    service = _interposed_service(migrated_engine, lambda: mutator(migrated_engine))
    if label == "alias":
        with pytest.raises(ValueError, match="stale"):
            service.confirm_claim(
                _result(),
                _claim(),
                _report(),
                IdentitySelection(mode=SelectionMode.NEW_COMPOUND),
                _actor(),
            )
    else:
        service.confirm_claim(
            _result(),
            _claim(),
            _report(),
            IdentitySelection(mode=SelectionMode.NEW_COMPOUND),
            _actor(),
        )
    with UnitOfWork(migrated_engine) as uow:
        if label == "alias":
            assert uow.aliases.list_by_batch(BATCH_ID) == ()
            assert uow.audit_events.list_by_batch(BATCH_ID) == ()
        else:
            assert len(uow.aliases.list_by_batch(BATCH_ID)) == 1
            event = uow.audit_events.list_by_batch(BATCH_ID)[0]
            assert json.loads(event.new_value_json or "{}")["reuse_after_race"] is True


def test_confirm_result_and_claim_smiles_are_mutually_required_before_uow(
    migrated_engine: Engine,
) -> None:
    uow_calls: list[int] = []
    index_calls: list[int] = []
    service = _service(
        migrated_engine, factory_calls=uow_calls, index_calls=index_calls
    )
    with pytest.raises(ValueError, match="SMILES"):
        service.confirm_claim(
            _result(),
            _claim(smiles=None),
            _report(),
            IdentitySelection(mode=SelectionMode.NEW_COMPOUND),
            _actor(),
        )
    with pytest.raises(ValueError, match="SMILES"):
        service.confirm_claim(
            None,
            _claim(),
            _report(ResolutionKind.ALIAS_ONLY),
            IdentitySelection(
                mode=SelectionMode.EXISTING_TARGET, compound_id=COMPOUND_ID
            ),
            _actor(ActorKind.USER),
        )
    with pytest.raises(ValueError, match="source"):
        service.confirm_claim(
            _result(source_smiles="CCN"),
            _claim(),
            _report(),
            IdentitySelection(mode=SelectionMode.NEW_COMPOUND),
            _actor(),
        )
    assert uow_calls == []
    assert index_calls == []


def test_structural_user_actor_may_omit_rationale_and_malformed_actor_is_safe(
    migrated_engine: Engine,
) -> None:
    _seed_project_batch(migrated_engine)
    actor = IdentityActor(kind=ActorKind.USER, actor_id="reviewer")
    service = _service(migrated_engine)
    service.confirm_claim(
        _result(),
        _claim(),
        _report(),
        IdentitySelection(mode=SelectionMode.NEW_COMPOUND),
        actor,
    )
    with UnitOfWork(migrated_engine) as uow:
        alias = uow.aliases.list_by_batch(BATCH_ID)[0]
        root = uow.identity_resolutions.list_by_alias(alias.id)[0]
    with pytest.raises(ValueError, match="actor"):
        service.retract(
            alias.id,
            root.id,
            {"kind": "user", "actor_id": "reviewer"},
        )


@pytest.mark.parametrize(
    "point",
    (
        "before_chemistry",
        "after_state",
        "after_alias_resolution",
        "before_audit",
    ),
)
def test_confirm_failpoints_roll_back_all_identity_categories(
    migrated_engine: Engine, point: str
) -> None:
    _seed_project_batch(migrated_engine)

    def failpoint(current: str) -> None:
        if current == point:
            raise RuntimeError("bounded failpoint")

    with pytest.raises(RuntimeError, match="bounded failpoint"):
        _service(migrated_engine, failpoint=failpoint).confirm_claim(
            _result(),
            _claim(),
            _report(),
            IdentitySelection(mode=SelectionMode.NEW_COMPOUND),
            _actor(),
        )
    with UnitOfWork(migrated_engine) as uow:
        assert uow.compounds.get(COMPOUND_ID) is None
        assert uow.molecular_states.get(STATE_ID) is None
        assert uow.aliases.list_by_batch(BATCH_ID) == ()
        assert uow.identity_resolutions.list_all() == ()
        assert uow.audit_events.list_by_batch(BATCH_ID) == ()


def test_confirm_rejects_missing_persistence_triple_before_uow_creation(
    migrated_engine: Engine,
) -> None:
    calls: list[int] = []
    service = _service(migrated_engine, factory_calls=calls)
    selection = IdentitySelection(mode=SelectionMode.NEW_COMPOUND)
    with pytest.raises(ValueError, match="persistence"):
        service.confirm_claim(
            _result(), _claim(batch_id=None), _report(), selection, _actor()
        )
    with pytest.raises(ValueError, match="persistence"):
        service.confirm_claim(
            _result(),
            _claim(source_system=None, source_value=None),
            _report(),
            selection,
            _actor(),
        )
    assert calls == []


def test_alias_only_binds_reported_compound_without_materializing_result(
    migrated_engine: Engine,
) -> None:
    _seed_project_batch(migrated_engine)
    existing = _result()
    with UnitOfWork(migrated_engine) as uow:
        uow.compounds.add(existing.compound)
        uow.molecular_states.add(existing.molecular_state)
        prior_batch = _batch().model_copy(
            update={"id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"}
        )
        uow.import_batches.add(prior_batch)
        prior_alias = uow.aliases.add(
            Alias(
                source_system="gold",
                source_value="ligand-1",
                import_batch_id=prior_batch.id,
                created_at=NOW,
            )
        )
        uow.identity_resolutions.add(
            IdentityResolution(
                alias_id=prior_alias.id,
                decision=IdentityDecision.CONFIRMED,
                compound_id=COMPOUND_ID,
                molecular_state_id=STATE_ID,
                decided_at=NOW,
                actor_kind=ActorKind.SYSTEM,
            )
        )
    candidate = ResolutionCandidate(
        compound_id=COMPOUND_ID, molecular_state_id=STATE_ID
    )
    result = _result(
        compound_id="77777777-7777-4777-8777-777777777777",
        state_id="88888888-8888-4888-8888-888888888888",
        structure_hash="c" * 64,
        state_hash="d" * 64,
    )
    resolution = _service(migrated_engine).confirm_claim(
        None,
        _claim(smiles=None),
        _report(ResolutionKind.ALIAS_ONLY, candidate=candidate),
        IdentitySelection(mode=SelectionMode.EXISTING_TARGET, compound_id=COMPOUND_ID),
        _actor(ActorKind.USER),
    )
    assert resolution.compound_id == COMPOUND_ID
    with UnitOfWork(migrated_engine) as uow:
        assert uow.compounds.get(result.compound.id) is None
        assert uow.molecular_states.get(result.molecular_state.id) is None


def test_exact_state_reuses_only_reported_state_and_new_state_binds_parent(
    migrated_engine: Engine,
) -> None:
    _seed_project_batch(migrated_engine)
    result = _result()
    with UnitOfWork(migrated_engine) as uow:
        uow.compounds.add(result.compound)
        uow.molecular_states.add(result.molecular_state)
    exact = _report(
        ResolutionKind.EXACT_STATE,
        candidate=ResolutionCandidate(
            compound_id=COMPOUND_ID, molecular_state_id=STATE_ID
        ),
        dormant=True,
    )
    resolved = _service(migrated_engine).confirm_claim(
        result,
        _claim(),
        exact,
        IdentitySelection(
            mode=SelectionMode.EXISTING_TARGET,
            compound_id=COMPOUND_ID,
            molecular_state_id=STATE_ID,
        ),
        _actor(),
    )
    assert resolved.molecular_state_id == STATE_ID

    second_result = _result(
        state_id="77777777-7777-4777-8777-777777777777", state_hash="c" * 64
    )
    new_state = _report(
        ResolutionKind.NEW_STATE,
        candidate=ResolutionCandidate(compound_id=COMPOUND_ID),
    )
    resolved_state = _service(migrated_engine).confirm_claim(
        second_result,
        _claim(source_value="ligand-2"),
        new_state,
        IdentitySelection(mode=SelectionMode.EXISTING_TARGET, compound_id=COMPOUND_ID),
        _actor(),
    )
    assert resolved_state.compound_id == COMPOUND_ID
    assert resolved_state.molecular_state_id == second_result.molecular_state.id
    with UnitOfWork(migrated_engine) as uow:
        stored = uow.molecular_states.get(second_result.molecular_state.id)
        assert stored is not None and stored.compound_id == COMPOUND_ID


def test_confirm_rejects_sibling_selection_and_result_hash_mismatch(
    migrated_engine: Engine,
) -> None:
    _seed_project_batch(migrated_engine)
    result = _result()
    with UnitOfWork(migrated_engine) as uow:
        uow.compounds.add(result.compound)
        uow.molecular_states.add(result.molecular_state)
    report = _report(
        ResolutionKind.EXACT_STATE,
        candidate=ResolutionCandidate(
            compound_id=COMPOUND_ID, molecular_state_id=STATE_ID
        ),
    )
    with pytest.raises(ValueError, match="selection"):
        _service(migrated_engine).confirm_claim(
            result,
            _claim(),
            report,
            IdentitySelection(
                mode=SelectionMode.EXISTING_TARGET,
                compound_id=COMPOUND_ID,
                molecular_state_id="88888888-8888-4888-8888-888888888888",
            ),
            _actor(),
        )
    mismatch = _result(structure_hash="c" * 64)
    with pytest.raises(ValueError, match="stale"):
        _service(migrated_engine).confirm_claim(
            mismatch,
            _claim(source_value="ligand-2"),
            report,
            IdentitySelection(
                mode=SelectionMode.EXISTING_TARGET,
                compound_id=COMPOUND_ID,
                molecular_state_id=STATE_ID,
            ),
            _actor(),
        )


def test_confirm_rejects_unresolved_and_authority_mismatch(
    migrated_engine: Engine,
) -> None:
    _seed_project_batch(migrated_engine)
    with pytest.raises(ValueError, match="SMILES"):
        _service(migrated_engine).confirm_claim(
            None,
            _claim(),
            _report(ResolutionKind.UNRESOLVED),
            IdentitySelection(
                mode=SelectionMode.EXISTING_TARGET, compound_id=COMPOUND_ID
            ),
            _actor(ActorKind.USER),
        )
    with pytest.raises(ValueError, match="selection"):
        _service(migrated_engine).confirm_claim(
            _result(),
            _claim(),
            _report(),
            IdentitySelection(
                mode=SelectionMode.EXISTING_TARGET, compound_id=COMPOUND_ID
            ),
            _actor(),
        )


def test_report_free_retract_and_restore_append_audited_successors(
    migrated_engine: Engine,
) -> None:
    _seed_project_batch(migrated_engine)
    service = _service(migrated_engine)
    service.confirm_claim(
        _result(),
        _claim(),
        _report(),
        IdentitySelection(mode=SelectionMode.NEW_COMPOUND),
        _actor(),
    )
    with UnitOfWork(migrated_engine) as uow:
        alias = uow.aliases.list_by_batch(BATCH_ID)[0]
        root = uow.identity_resolutions.list_by_alias(alias.id)[0]
    retract = service.retract(alias.id, root.id, _actor(ActorKind.USER))
    assert retract.decision is IdentityDecision.RETRACTED
    restored = service.restore(
        alias.id,
        retract.id,
        IdentitySelection(mode=SelectionMode.EXISTING_TARGET, compound_id=COMPOUND_ID),
        _actor(ActorKind.USER),
    )
    assert restored.decision is IdentityDecision.RESTORED
    with UnitOfWork(migrated_engine) as uow:
        history = uow.identity_resolutions.list_by_alias(alias.id)
        assert {item.decision for item in history} == {
            IdentityDecision.CONFIRMED,
            IdentityDecision.RETRACTED,
            IdentityDecision.RESTORED,
        }
        assert len(uow.audit_events.list_by_batch(BATCH_ID)) == 3


def test_confirm_rejects_missing_and_rolled_back_batches_and_invalid_authority(
    migrated_engine: Engine,
) -> None:
    _seed_project_batch(migrated_engine)
    service = _service(migrated_engine)
    with pytest.raises(RecordNotFoundError, match="batch"):
        service.confirm_claim(
            _result(),
            _claim(batch_id="77777777-7777-4777-8777-777777777777"),
            _report(),
            IdentitySelection(mode=SelectionMode.NEW_COMPOUND),
            _actor(),
        )
    with UnitOfWork(migrated_engine) as uow:
        uow.import_batches.rollback(BATCH_ID, rollback_reason="withdrawn")
    with pytest.raises(ValueError, match="rolled-back"):
        service.confirm_claim(
            _result(),
            _claim(),
            _report(),
            IdentitySelection(mode=SelectionMode.NEW_COMPOUND),
            _actor(),
        )
    with pytest.raises(ValueError, match="SMILES"):
        service.confirm_claim(
            None,
            _claim(batch_id="77777777-7777-4777-8777-777777777777"),
            _report(
                ResolutionKind.EXACT_STATE,
                candidate=ResolutionCandidate(
                    compound_id=COMPOUND_ID, molecular_state_id=STATE_ID
                ),
            ),
            IdentitySelection(
                mode=SelectionMode.EXISTING_TARGET,
                compound_id=COMPOUND_ID,
                molecular_state_id=STATE_ID,
            ),
            _actor(),
        )


def test_transition_rejects_rolled_back_batch_before_append_or_audit(
    migrated_engine: Engine,
) -> None:
    _seed_project_batch(migrated_engine)
    service = _service(migrated_engine)
    service.confirm_claim(
        _result(),
        _claim(),
        _report(),
        IdentitySelection(mode=SelectionMode.NEW_COMPOUND),
        _actor(),
    )
    with UnitOfWork(migrated_engine) as uow:
        alias = uow.aliases.list_by_batch(BATCH_ID)[0]
        root = uow.identity_resolutions.list_by_alias(alias.id)[0]
        uow.import_batches.rollback(BATCH_ID, rollback_reason="withdrawn")
    with pytest.raises(ValueError, match="rolled-back"):
        service.retract(alias.id, root.id, _actor(ActorKind.USER))
    with UnitOfWork(migrated_engine) as uow:
        assert len(uow.identity_resolutions.list_by_alias(alias.id)) == 1
        assert len(uow.audit_events.list_by_batch(BATCH_ID)) == 1


def test_transition_validation_rejects_non_leaf_missing_and_unowned_targets(
    migrated_engine: Engine,
) -> None:
    _seed_project_batch(migrated_engine)
    service = _service(migrated_engine)
    service.confirm_claim(
        _result(),
        _claim(),
        _report(),
        IdentitySelection(mode=SelectionMode.NEW_COMPOUND),
        _actor(),
    )
    with UnitOfWork(migrated_engine) as uow:
        alias = uow.aliases.list_by_batch(BATCH_ID)[0]
        root = uow.identity_resolutions.list_by_alias(alias.id)[0]
    user = _actor(ActorKind.USER)
    with pytest.raises(ValueError, match="existing selection"):
        service.reassign(
            alias.id, root.id, IdentitySelection(mode=SelectionMode.NEW_COMPOUND), user
        )
    with pytest.raises(ValueError, match="existing selection"):
        service.restore(
            alias.id, root.id, IdentitySelection(mode=SelectionMode.NEW_COMPOUND), user
        )
    with pytest.raises(RecordNotFoundError, match="predecessor"):
        service.retract("77777777-7777-4777-8777-777777777777", root.id, user)
    with pytest.raises(RecordNotFoundError, match="selected compound"):
        service.reassign(
            alias.id,
            root.id,
            IdentitySelection(
                mode=SelectionMode.EXISTING_TARGET,
                compound_id="77777777-7777-4777-8777-777777777777",
            ),
            user,
        )
    with UnitOfWork(migrated_engine) as uow:
        other = _result(
            compound_id="88888888-8888-4888-8888-888888888888",
            state_id="99999999-9999-4999-8999-999999999999",
            structure_hash="c" * 64,
            state_hash="d" * 64,
        )
        uow.compounds.add(other.compound)
        uow.molecular_states.add(other.molecular_state)
    with pytest.raises(ValueError, match="owned"):
        service.reassign(
            alias.id,
            root.id,
            IdentitySelection(
                mode=SelectionMode.EXISTING_TARGET,
                compound_id=COMPOUND_ID,
                molecular_state_id="99999999-9999-4999-8999-999999999999",
            ),
            user,
        )
    with pytest.raises(ValueError, match="retracted"):
        service.restore(
            alias.id,
            root.id,
            IdentitySelection(
                mode=SelectionMode.EXISTING_TARGET, compound_id=COMPOUND_ID
            ),
            user,
        )
    retract = service.retract(alias.id, root.id, user)
    with pytest.raises(IdentityResolutionConflictError, match="conflicts"):
        service.retract(alias.id, root.id, user)
    assert retract.decision is IdentityDecision.RETRACTED
