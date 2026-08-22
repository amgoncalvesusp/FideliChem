"""End-to-end acceptance tests for the import pipeline using FakeAdapter."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from fidelichem.adapters.fake import FakeAdapter
from fidelichem.adapters.registry import AdapterRegistry
from fidelichem.chemistry.service import ChemistryService
from fidelichem.domain.chemistry import (
    IdentityActor,
    IdentityDecision,
)
from fidelichem.domain.errors import (
    DuplicateImportError,
    ImportValidationError,
)
from fidelichem.domain.models import (
    ActorKind,
    ImportStatus,
    Project,
)
from fidelichem.identity.service import IdentityService
from fidelichem.importers.manager import ImportManager
from fidelichem.storage.engine import create_sqlite_engine
from fidelichem.storage.identity_index import PersistentIdentityIndex
from fidelichem.storage.runner import upgrade_database
from fidelichem.storage.session import UnitOfWork


@pytest.fixture
def test_environment(tmp_path: Path):
    db_path = tmp_path / "project.fidelichem.sqlite"
    engine = create_sqlite_engine(db_path)
    upgrade_database(engine)

    def _uow_factory() -> UnitOfWork:
        return UnitOfWork(engine)

    def _index_factory() -> PersistentIdentityIndex:
        return PersistentIdentityIndex(engine)

    def clock() -> datetime:
        return datetime(2026, 8, 22, 12, 0, 0, tzinfo=UTC)

    identity_service = IdentityService(
        uow_factory=_uow_factory,
        index_factory=_index_factory,
        clock=clock,
    )
    chemistry_service = ChemistryService()

    registry = AdapterRegistry()
    registry.register(FakeAdapter())

    manager = ImportManager(
        registry=registry,
        uow_factory=_uow_factory,
        identity_service=identity_service,
        chemistry_service=chemistry_service,
        clock=clock,
    )

    now = datetime(2026, 8, 22, 12, 0, 0, tzinfo=UTC)
    with _uow_factory() as uow:
        project = uow.projects.add(
            Project(name="Acceptance Pipeline", created_at=now, updated_at=now)
        )

    # Create mock dataset directory on disk
    data_dir = tmp_path / "dataset"
    data_dir.mkdir()

    manifest_content = {
        "format": "fake_docking_v1",
        "target": {"name": "Beta-Lactamase", "pdb_id": "1XYZ"},
        "docking_run": {"run_name": "Run_Alpha", "engine": "FakeDockEngine"},
        "compounds": [
            {
                "source_system": "fake_db",
                "source_value": "CMPD_01",
                "smiles": "CC(=O)Oc1ccccc1C(=O)O",  # Aspirin
                "pose_id": "pose_1",
                "rank": 1,
                "score": -9.4,
            },
            {
                "source_system": "fake_db",
                "source_value": "CMPD_02",
                "smiles": "CC(=O)Nc1ccc(O)cc1",  # Paracetamol
                "pose_id": "pose_2",
                "rank": 1,
                "score": -7.8,
            },
            {
                "source_system": "fake_db",
                "source_value": "CMPD_03_NO_SCORE",
                "smiles": "c1ccccc1",  # Benzene
                "pose_id": "pose_3",
                "rank": 2,
                "score": None,  # Explicit missing score
            },
        ],
    }
    (data_dir / "manifest.fake.json").write_text(
        json.dumps(manifest_content, indent=2), encoding="utf-8"
    )

    try:
        yield manager, project.id, data_dir, _uow_factory, _index_factory
    finally:
        engine.dispose()


def test_e2e_fake_adapter_full_lifecycle(test_environment) -> None:
    manager, project_id, data_dir, uow_factory, index_factory = test_environment

    # 1. Detection
    reports = manager.detect(data_dir)
    assert len(reports) == 1
    assert reports[0].suggested_adapter == "fidelichem.fake"
    assert reports[0].confidence >= 0.9

    # 2. Plan
    plan = manager.plan("fidelichem.fake", data_dir)
    assert plan.adapter_id == "fidelichem.fake"
    assert "manifest.fake.json" in plan.source_files

    # 3. Dry-run
    dry_run_res = manager.execute_import(project_id, plan, dry_run=True)
    assert dry_run_res.validation.is_valid
    assert len(dry_run_res.bundle.compounds) == 3

    with uow_factory() as uow:
        assert len(uow.import_batches.list_by_project(project_id)) == 0

    # 4. Ingestion execution
    actor = IdentityActor(kind=ActorKind.USER, actor_id="lead_investigator")
    result = manager.execute_import(project_id, plan, actor=actor)

    assert result.batch.status == ImportStatus.COMPLETED
    assert result.batch.file_count == 1
    assert len(result.confirmed_resolutions) == 3
    for res in result.confirmed_resolutions:
        assert res.decision is IdentityDecision.CONFIRMED

    # 5. Database state verification
    with uow_factory() as uow:
        # Batch verification
        batch = uow.import_batches.get(result.batch.id)
        assert batch is not None
        assert batch.status == ImportStatus.COMPLETED
        assert batch.input_hash == plan.plan_hash

        # Source artifact verification
        artifacts = uow.source_artifacts.list_by_batch(result.batch.id)
        assert len(artifacts) == 1
        assert artifacts[0].relative_path == "manifest.fake.json"

        # Chemical alias verification
        aliases = uow.aliases.list_by_batch(result.batch.id)
        assert len(aliases) == 3
        alias_values = {a.source_value for a in aliases}
        assert alias_values == {"CMPD_01", "CMPD_02", "CMPD_03_NO_SCORE"}

        # Audit event verification
        audit_events = uow.audit_events.list_by_batch(result.batch.id)
        assert any(e.action == "import.completed" for e in audit_events)
        assert any(e.actor_id == "lead_investigator" for e in audit_events)

    # 6. Index query verification
    index = index_factory()
    entry1 = index.active_by_alias("fake_db", "CMPD_01")
    assert len(entry1) >= 1
    assert entry1[0].compound_id is not None

    entry2 = index.active_by_alias("fake_db", "CMPD_02")
    assert len(entry2) >= 1

    # 7. Duplicate import rejection
    with pytest.raises(DuplicateImportError, match="Duplicate import detected"):
        manager.execute_import(project_id, plan)

    # 8. Rollback execution
    rolled_back = manager.rollback_import(
        project_id,
        result.batch.id,
        reason="Dataset contained incorrect experimental scores",
        actor=actor,
    )
    assert rolled_back.status == ImportStatus.ROLLED_BACK

    with uow_factory() as uow:
        batch_after_rollback = uow.import_batches.get(result.batch.id)
        assert batch_after_rollback is not None
        assert batch_after_rollback.status == ImportStatus.ROLLED_BACK

        rollback_events = uow.audit_events.list_by_batch(result.batch.id)
        assert any(e.action == "import.rolled_back" for e in rollback_events)

    # Index must no longer return active targets for rolled-back batch
    index_after_rollback = index_factory()
    assert len(index_after_rollback.active_by_alias("fake_db", "CMPD_01")) == 0

    # 9. Re-import after rollback succeeds
    reimported = manager.execute_import(project_id, plan, actor=actor)
    assert reimported.batch.status == ImportStatus.COMPLETED
    assert reimported.batch.id != result.batch.id

    index_after_reimport = index_factory()
    assert len(index_after_reimport.active_by_alias("fake_db", "CMPD_01")) >= 1


def test_fake_adapter_rejects_corrupted_json(test_environment) -> None:
    manager, project_id, data_dir, uow_factory, index_factory = test_environment

    # Corrupt the json file
    (data_dir / "manifest.fake.json").write_text("NOT VALID JSON {[[", encoding="utf-8")

    plan = manager.plan("fidelichem.fake", data_dir)
    with pytest.raises(ImportValidationError):
        manager.execute_import(project_id, plan)
