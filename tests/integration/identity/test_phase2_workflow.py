from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import Engine, text

from fidelichem.chemistry import ChemistryService
from fidelichem.domain.chemistry import (
    ChemistryWarningCode,
    IdentityActor,
    IdentityClaim,
    IdentityDecision,
    IdentitySelection,
    SelectionMode,
)
from fidelichem.domain.errors import (
    AmbiguousParentStructureError,
    IdentityResolutionConflictError,
    TautomerEnumerationLimitError,
)
from fidelichem.domain.models import ActorKind, ImportBatch
from fidelichem.identity.models import EvidenceKind, ResolutionKind
from fidelichem.identity.resolver import IdentityResolver
from fidelichem.identity.service import IdentityService
from fidelichem.projects import create_project, open_project
from fidelichem.storage.identity_index import PersistentIdentityIndex
from fidelichem.storage.services import StorageService
from fidelichem.storage.session import UnitOfWork

NOW = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)


def _service(engine: Engine, calls: list[int] | None = None) -> IdentityService:
    def make_uow() -> UnitOfWork:
        if calls is not None:
            calls.append(1)
        return UnitOfWork(engine)

    return IdentityService(
        uow_factory=make_uow,
        index_factory=lambda: PersistentIdentityIndex(engine),
        clock=lambda: NOW,
    )


def _batch(project_id: str) -> ImportBatch:
    return ImportBatch(
        project_id=project_id,
        adapter_id="phase2-workflow",
        adapter_version="1",
        started_at=NOW,
        source_root="workflow-inputs",
    )


def _claim(
    batch_id: str | None,
    *,
    source_value: str,
    smiles: str | None,
    inchikey: str | None = None,
    source_system: str | None = "gold",
) -> IdentityClaim:
    return IdentityClaim(
        source_system=source_system,
        source_value=source_value if source_system is not None else None,
        smiles=smiles,
        inchikey=inchikey,
        import_batch_id=batch_id,
    )


def _user() -> IdentityActor:
    return IdentityActor(
        kind=ActorKind.USER,
        actor_id="phase2-reviewer",
        rationale="explicit integration workflow review",
    )


def _system() -> IdentityActor:
    return IdentityActor(kind=ActorKind.SYSTEM)


def _counts(engine: Engine) -> tuple[int, ...]:
    tables = (
        "compound",
        "molecular_state",
        "alias",
        "identity_resolution",
        "audit_event",
    )
    with engine.connect() as connection:
        return tuple(
            int(connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one())
            for table in tables
        )


def _candidate(report, *, state: bool):
    return next(
        candidate
        for candidate in report.candidates
        if (candidate.molecular_state_id is not None) is state
    )


def _assert_dormant_identity(
    engine: Engine,
    chemistry: ChemistryService,
    resolver: IdentityResolver,
    state_id: str,
) -> None:
    index = PersistentIdentityIndex(engine)
    assert index.active_by_alias("gold", "ligand-1") == ()
    result = chemistry.canonicalize("CN.[Cl-]", created_at=NOW)
    report = resolver.resolve(
        result,
        _claim(None, source_value="post-lifecycle", smiles="CN.[Cl-]"),
        index,
    )
    assert report.kind is ResolutionKind.EXACT_STATE
    assert report.catalog_match_dormant is True
    assert any(
        candidate.molecular_state_id == state_id and candidate.catalog_dormant
        for candidate in report.candidates
    )


def test_phase2_project_reopen_workflow_is_atomic_and_reversible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "phase-two-project"
    project = create_project(root, "Phase 2 workflow")
    assert project.project is not None
    assert project.engine is not None
    engine = project.engine
    storage = StorageService(engine)
    chemistry = ChemistryService()
    resolver = IdentityResolver()

    first_batch = _batch(project.project.id)
    storage.create_import_batch(first_batch)
    mapped_source = "[CH3:7][NH2:2].[Cl-]"
    mapped_result = chemistry.canonicalize(mapped_source, created_at=NOW)
    assert mapped_result.source_smiles == mapped_source
    assert ":" not in mapped_result.molecular_state.state_smiles
    first_claim = _claim(first_batch.id, source_value="ligand-1", smiles=mapped_source)
    first_report = resolver.resolve(
        mapped_result, first_claim, PersistentIdentityIndex(engine)
    )
    assert first_report.kind is ResolutionKind.NEW_COMPOUND
    first_resolution = _service(engine).confirm_claim(
        mapped_result,
        first_claim,
        first_report,
        IdentitySelection(mode=SelectionMode.NEW_COMPOUND),
        _system(),
    )
    assert first_resolution.decision is IdentityDecision.CONFIRMED

    with UnitOfWork(engine) as uow:
        stored_compound = uow.compounds.get(mapped_result.compound.id)
        stored_state = uow.molecular_states.get(mapped_result.molecular_state.id)
        stored_aliases = uow.aliases.list_by_batch(first_batch.id)
        assert stored_compound == mapped_result.compound
        assert stored_state == mapped_result.molecular_state
        assert len(stored_aliases) == 1
        assert uow.identity_resolutions.list_by_alias(stored_aliases[0].id) == (
            first_resolution,
        )
        first_events = uow.audit_events.list_by_batch(first_batch.id)
        assert len(first_events) == 2
        assert first_events[-1].import_batch_id == first_batch.id

    project.close()
    reopened = open_project(root)
    assert reopened.project is not None
    assert reopened.engine is not None
    engine = reopened.engine

    equivalent_source = "CN.[Cl-]"
    equivalent_result = chemistry.canonicalize(equivalent_source, created_at=NOW)
    equivalent_claim = _claim(
        first_batch.id, source_value="unmapped-equivalent", smiles=equivalent_source
    )
    equivalent_report = resolver.resolve(
        equivalent_result, equivalent_claim, PersistentIdentityIndex(engine)
    )
    assert equivalent_report.kind is ResolutionKind.EXACT_STATE
    assert equivalent_report.catalog_match_dormant is False
    exact_candidate = _candidate(equivalent_report, state=True)
    assert exact_candidate.compound_id == mapped_result.compound.id
    assert exact_candidate.molecular_state_id == mapped_result.molecular_state.id

    unavailable_batch = _batch(reopened.project.id)
    storage = StorageService(engine)
    storage.create_import_batch(unavailable_batch)
    import fidelichem.chemistry.service as chemistry_module

    monkeypatch.setattr(chemistry_module.inchi, "MolToInchiKey", lambda _mol: "")
    unavailable_source = "C[NH3+].[Cl-]"
    unavailable_result = chemistry.canonicalize(unavailable_source, created_at=NOW)
    assert unavailable_result.compound.inchikey is None
    assert unavailable_result.molecular_state.state_inchikey is None
    assert any(
        warning.code is ChemistryWarningCode.INCHI_UNAVAILABLE
        for warning in unavailable_result.warnings
    )
    unavailable_claim = _claim(
        unavailable_batch.id, source_value="unavailable", smiles=unavailable_source
    )
    unavailable_report = resolver.resolve(
        unavailable_result,
        unavailable_claim,
        PersistentIdentityIndex(engine),
    )
    assert unavailable_report.kind is ResolutionKind.NEW_STATE
    parent_candidate = _candidate(unavailable_report, state=False)
    assert parent_candidate.compound_id == mapped_result.compound.id
    unavailable_resolution = _service(engine).confirm_claim(
        unavailable_result,
        unavailable_claim,
        unavailable_report,
        IdentitySelection(
            mode=SelectionMode.EXISTING_TARGET,
            compound_id=parent_candidate.compound_id,
        ),
        _system(),
    )
    assert unavailable_resolution.decision is IdentityDecision.CONFIRMED
    with UnitOfWork(engine) as uow:
        payload = json.loads(
            uow.audit_events.list_by_batch(unavailable_batch.id)[-1].new_value_json
            or "{}"
        )
        assert payload["warnings"] == [ChemistryWarningCode.INCHI_UNAVAILABLE.value]
        assert payload["inchi_unavailable"] is True
        assert payload["inchi_version"] is not None

    monkeypatch.undo()

    other_batch = _batch(reopened.project.id)
    storage.create_import_batch(other_batch)
    other_source = "CCN"
    other_result = chemistry.canonicalize(other_source, created_at=NOW)
    other_claim = _claim(other_batch.id, source_value="other", smiles=other_source)
    other_report = resolver.resolve(
        other_result, other_claim, PersistentIdentityIndex(engine)
    )
    assert other_report.kind is ResolutionKind.NEW_COMPOUND
    other_resolution = _service(engine).confirm_claim(
        other_result,
        other_claim,
        other_report,
        IdentitySelection(mode=SelectionMode.NEW_COMPOUND),
        _system(),
    )
    other_compound_id = other_resolution.compound_id
    assert other_compound_id is not None

    alias_batch = _batch(reopened.project.id)
    storage.create_import_batch(alias_batch)
    alias_claim = _claim(alias_batch.id, source_value="unavailable", smiles=None)
    alias_report = resolver.resolve(None, alias_claim, PersistentIdentityIndex(engine))
    assert alias_report.kind is ResolutionKind.ALIAS_ONLY
    alias_candidate = _candidate(alias_report, state=True)
    before_alias_only = _counts(engine)
    alias_resolution = _service(engine).confirm_claim(
        None,
        alias_claim,
        alias_report,
        IdentitySelection(
            mode=SelectionMode.EXISTING_TARGET,
            compound_id=alias_candidate.compound_id,
        ),
        _user(),
    )
    assert alias_resolution.molecular_state_id is None
    after_alias_only = _counts(engine)
    assert after_alias_only[:2] == before_alias_only[:2]
    assert after_alias_only[2:] == tuple(value + 1 for value in before_alias_only[2:])

    # Resolver-only claims remain valid, while persistence prerequisites fail
    # before IdentityService opens a UnitOfWork.
    resolver_only_claim = _claim(None, source_value="ligand-1", smiles=None)
    resolver_only_report = resolver.resolve(
        None, resolver_only_claim, PersistentIdentityIndex(engine)
    )
    assert resolver_only_report.kind is ResolutionKind.ALIAS_ONLY
    null_source_claim = IdentityClaim()
    assert (
        resolver.resolve(None, null_source_claim, PersistentIdentityIndex(engine)).kind
        is ResolutionKind.UNRESOLVED
    )
    calls: list[int] = []
    guarded_service = _service(engine, calls)
    alias_selection = IdentitySelection(
        mode=SelectionMode.EXISTING_TARGET,
        compound_id=alias_candidate.compound_id,
    )
    existing_batch_null_source_claim = IdentityClaim(import_batch_id=first_batch.id)
    assert (
        resolver.resolve(
            None,
            existing_batch_null_source_claim,
            PersistentIdentityIndex(engine),
        ).kind
        is ResolutionKind.UNRESOLVED
    )
    with pytest.raises(ValueError, match="persistence prerequisites"):
        guarded_service.confirm_claim(
            None,
            existing_batch_null_source_claim,
            resolver_only_report,
            alias_selection,
            _user(),
        )
    with pytest.raises(ValueError, match="persistence prerequisites"):
        guarded_service.confirm_claim(
            None,
            resolver_only_claim,
            resolver_only_report,
            alias_selection,
            _user(),
        )
    with pytest.raises(ValueError, match="persistence prerequisites"):
        guarded_service.confirm_claim(
            None, null_source_claim, resolver_only_report, alias_selection, _user()
        )
    assert calls == []

    arbitrary_batch = _batch(reopened.project.id)
    storage.create_import_batch(arbitrary_batch)
    arbitrary_claim = _claim(arbitrary_batch.id, source_value="ligand-1", smiles=None)
    arbitrary_report = resolver.resolve(
        None,
        arbitrary_claim,
        PersistentIdentityIndex(engine),
    )
    assert arbitrary_report.kind is ResolutionKind.ALIAS_ONLY
    with pytest.raises(ValueError, match="selection"):
        _service(engine).confirm_claim(
            None,
            arbitrary_claim,
            arbitrary_report,
            IdentitySelection(
                mode=SelectionMode.EXISTING_TARGET,
                compound_id=other_compound_id,
            ),
            _user(),
        )
    with UnitOfWork(engine) as uow:
        assert uow.aliases.list_by_batch(arbitrary_batch.id) == ()
        arbitrary_events = uow.audit_events.list_by_batch(arbitrary_batch.id)
        assert len(arbitrary_events) == 1
        assert arbitrary_events[0].action == "import.created"

    invalid_batch = _batch(reopened.project.id)
    storage.create_import_batch(invalid_batch)
    before_invalid = _counts(engine)
    with pytest.raises(AmbiguousParentStructureError):
        chemistry.canonicalize("CCO.CN", created_at=NOW)

    class IncompleteEnumerator:
        def SetMaxTautomers(self, _value: int) -> None:
            return None

        def SetMaxTransforms(self, _value: int) -> None:
            return None

        def Enumerate(self, _mol: object) -> SimpleNamespace:
            return SimpleNamespace(status="Limit")

    monkeypatch.setattr(
        chemistry_module.rdMolStandardize,
        "TautomerEnumerator",
        IncompleteEnumerator,
    )
    with pytest.raises(TautomerEnumerationLimitError):
        chemistry.canonicalize("CCO", created_at=NOW)
    assert _counts(engine) == before_invalid
    with UnitOfWork(engine) as uow:
        assert uow.aliases.list_by_batch(invalid_batch.id) == ()
        invalid_events = uow.audit_events.list_by_batch(invalid_batch.id)
        assert len(invalid_events) == 1
        assert invalid_events[0].action == "import.created"

    monkeypatch.undo()
    conflict_batch = _batch(reopened.project.id)
    storage.create_import_batch(conflict_batch)
    conflict_claim = _claim(
        conflict_batch.id,
        source_value="ligand-1",
        smiles=other_source,
        inchikey=other_result.molecular_state.state_inchikey,
    )
    conflict_report = resolver.resolve(
        other_result, conflict_claim, PersistentIdentityIndex(engine)
    )
    assert conflict_report.kind is ResolutionKind.CONFLICT
    assert any(
        EvidenceKind.ACTIVE_ALIAS in candidate.evidence
        for candidate in conflict_report.candidates
    )
    assert any(
        EvidenceKind.CATALOG_STATE in candidate.evidence
        for candidate in conflict_report.candidates
    )
    before_conflict = _counts(engine)
    with pytest.raises(ValueError, match="selection"):
        _service(engine).confirm_claim(
            other_result,
            conflict_claim,
            conflict_report,
            IdentitySelection(
                mode=SelectionMode.EXISTING_TARGET,
                compound_id=other_compound_id,
                molecular_state_id=mapped_result.molecular_state.id,
            ),
            _user(),
        )
    assert _counts(engine) == before_conflict
    with UnitOfWork(engine) as uow:
        assert uow.aliases.list_by_batch(conflict_batch.id) == ()
        assert uow.audit_events.list_by_batch(conflict_batch.id)[0].action == (
            "import.created"
        )

    valid_conflict_batch = _batch(reopened.project.id)
    storage.create_import_batch(valid_conflict_batch)
    valid_conflict_claim = _claim(
        valid_conflict_batch.id,
        source_value="unavailable",
        smiles=other_source,
        inchikey=other_result.molecular_state.state_inchikey,
    )
    valid_conflict_report = resolver.resolve(
        other_result,
        valid_conflict_claim,
        PersistentIdentityIndex(engine),
    )
    assert valid_conflict_report.kind is ResolutionKind.CONFLICT
    valid_conflict_candidate = next(
        candidate
        for candidate in valid_conflict_report.candidates
        if candidate.compound_id == other_compound_id
        and candidate.molecular_state_id is not None
    )
    valid_conflict_resolution = _service(engine).confirm_claim(
        other_result,
        valid_conflict_claim,
        valid_conflict_report,
        IdentitySelection(
            mode=SelectionMode.EXISTING_TARGET,
            compound_id=valid_conflict_candidate.compound_id,
            molecular_state_id=valid_conflict_candidate.molecular_state_id,
        ),
        _user(),
    )
    assert valid_conflict_resolution.compound_id == other_compound_id
    assert (
        valid_conflict_resolution.molecular_state_id
        == valid_conflict_candidate.molecular_state_id
    )
    with UnitOfWork(engine) as uow:
        valid_aliases = uow.aliases.list_by_batch(valid_conflict_batch.id)
        assert len(valid_aliases) == 1
        assert uow.identity_resolutions.list_by_alias(valid_aliases[0].id) == (
            valid_conflict_resolution,
        )
        valid_events = uow.audit_events.list_by_batch(valid_conflict_batch.id)
        assert len(valid_events) == 2
        valid_payload = json.loads(valid_events[-1].new_value_json or "{}")
        assert valid_payload["report_kind"] == ResolutionKind.CONFLICT.value
        assert valid_payload["structure_hash"] == other_result.compound.structure_hash
        assert valid_payload["state_hash"] == other_result.molecular_state.state_hash
        assert valid_payload["actor_kind"] == ActorKind.USER.value
        assert valid_payload["actor_id"] == "phase2-reviewer"
        assert valid_payload["rationale"] == _user().rationale
        assert valid_payload["selected_target"] == {
            "compound_id": other_compound_id,
            "molecular_state_id": valid_conflict_candidate.molecular_state_id,
        }

    first_alias = stored_aliases[0]
    first_root = first_resolution
    reassigned = _service(engine).reassign(
        first_alias.id,
        first_root.id,
        IdentitySelection(
            mode=SelectionMode.EXISTING_TARGET,
            compound_id=first_root.compound_id,
        ),
        _user(),
    )
    retracted = _service(engine).retract(first_alias.id, reassigned.id, _user())
    with pytest.raises(IdentityResolutionConflictError):
        _service(engine).retract(first_alias.id, reassigned.id, _user())
    restored = _service(engine).restore(
        first_alias.id,
        retracted.id,
        IdentitySelection(
            mode=SelectionMode.EXISTING_TARGET,
            compound_id=first_root.compound_id,
            molecular_state_id=first_root.molecular_state_id,
        ),
        _user(),
    )
    final_retracted = _service(engine).retract(first_alias.id, restored.id, _user())
    assert final_retracted.decision is IdentityDecision.RETRACTED

    _assert_dormant_identity(
        engine, chemistry, resolver, mapped_result.molecular_state.id
    )
    reopened.close()
    reopened = open_project(root)
    assert reopened.engine is not None
    engine = reopened.engine
    _assert_dormant_identity(
        engine, chemistry, resolver, mapped_result.molecular_state.id
    )
    storage.complete_import_batch(
        first_batch.id, completed_at=NOW + timedelta(minutes=1)
    )
    storage.rollback_import_batch(first_batch.id, reason="withdrawn in workflow")
    reopened.close()
    reopened = open_project(root)
    assert reopened.engine is not None
    engine = reopened.engine
    _assert_dormant_identity(
        engine, chemistry, resolver, mapped_result.molecular_state.id
    )
    with UnitOfWork(engine) as uow:
        assert uow.aliases.get(first_alias.id) is not None
        history = uow.identity_resolutions.list_by_alias(first_alias.id)
        assert len(history) == 5
        decisions = [item.decision for item in history]
        assert decisions.count(IdentityDecision.CONFIRMED) == 1
        assert decisions.count(IdentityDecision.REASSIGNED) == 1
        assert decisions.count(IdentityDecision.RESTORED) == 1
        assert decisions.count(IdentityDecision.RETRACTED) == 2
        assert reassigned.id in {item.id for item in history}
        assert retracted.id in {item.id for item in history}
        assert restored.id in {item.id for item in history}
        assert final_retracted.id in {item.id for item in history}
        assert retracted.supersedes_id == reassigned.id
        assert restored.supersedes_id == retracted.id
        assert final_retracted.supersedes_id == restored.id
        actions = [
            event.action for event in uow.audit_events.list_by_batch(first_batch.id)
        ]
        assert "identity.reassigned" in actions
        assert "identity.retracted" in actions
        assert "identity.restored" in actions
        assert actions[-1] == "import.rolled_back"
    reopened.close()
