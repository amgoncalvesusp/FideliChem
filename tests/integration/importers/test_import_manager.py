"""Integration tests for ImportManager execution and storage."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from fidelichem.adapters.base import build_import_plan, compute_source_artifacts
from fidelichem.adapters.registry import AdapterRegistry
from fidelichem.chemistry.service import ChemistryService
from fidelichem.domain.adapters import (
    DetectionReport,
    ImportBundle,
    ImportPlan,
    PoseRecord,
    QCIssue,
    QCSeverity,
    RawCompoundRecord,
    ScoreObservationRecord,
    SourceArtifactRecord,
    TargetRecord,
    ValidationReport,
)
from fidelichem.domain.chemistry import (
    IdentityActor,
)
from fidelichem.domain.errors import (
    DuplicateImportError,
    ImportValidationError,
)
from fidelichem.domain.models import ActorKind, ImportStatus, Project
from fidelichem.identity.service import IdentityService
from fidelichem.importers.manager import ImportManager
from fidelichem.storage.engine import create_sqlite_engine
from fidelichem.storage.identity_index import PersistentIdentityIndex
from fidelichem.storage.runner import upgrade_database
from fidelichem.storage.session import UnitOfWork


class TestScientificAdapter:
    adapter_id = "fidelichem.test_sci"
    adapter_version = "1.0.0"
    display_name = "Test Scientific Adapter"

    def probe(self, source: Path) -> DetectionReport:
        return DetectionReport(
            confidence=1.0,
            detected_format="test_sci",
            candidate_files=("compounds.csv", "scores.csv"),
            suggested_adapter=self.adapter_id,
        )

    def plan(
        self, source: Path, options: Mapping[str, Any] | None = None
    ) -> ImportPlan:
        artifacts = compute_source_artifacts(source, ["compounds.csv", "scores.csv"])
        return build_import_plan(
            adapter_id=self.adapter_id,
            adapter_version=self.adapter_version,
            source_root=str(source),
            artifacts=artifacts,
            options=options,
        )

    def parse(self, plan: ImportPlan) -> ImportBundle:
        sha_comp = next(h for p, h in plan.file_hashes if p == "compounds.csv")
        sha_scores = next(h for p, h in plan.file_hashes if p == "scores.csv")
        now = datetime(2026, 8, 22, 12, 0, 0, tzinfo=UTC)

        artifacts = (
            SourceArtifactRecord(
                relative_path="compounds.csv",
                sha256=sha_comp,
                size_bytes=128,
                file_type="csv",
                mtime=now,
            ),
            SourceArtifactRecord(
                relative_path="scores.csv",
                sha256=sha_scores,
                size_bytes=256,
                file_type="csv",
                mtime=now,
            ),
        )
        compounds = (
            RawCompoundRecord(
                source_system="test_run",
                source_value="ligand_001",
                source_smiles="CC(=O)Oc1ccccc1C(=O)O",  # Aspirin
                source_artifact_path="compounds.csv",
            ),
        )
        target = TargetRecord(name="TargetAlpha", pdb_id="1ABC")
        poses = (
            PoseRecord(
                run_name="Run1",
                compound_source_system="test_run",
                compound_source_value="ligand_001",
                source_pose_id="P1",
                rank=1,
            ),
        )

        scores = (
            ScoreObservationRecord(
                run_name="Run1",
                compound_source_value="ligand_001",
                source_pose_id="P1",
                score_key="docking.score",
                raw_value=75.5,
                source_artifact_path="scores.csv",
            ),
        )
        qc_messages = (
            QCIssue(
                code="QC_INFO_HEADER",
                message="File header parsed cleanly",
                severity=QCSeverity.INFO,
            ),
        )

        return ImportBundle(
            plan=plan,
            targets=(target,),
            compounds=compounds,
            docking_runs=(),
            poses=poses,
            scores=scores,
            source_artifacts=artifacts,
            qc_messages=qc_messages,
            provenance={"adapter": self.adapter_id},
        )

    def validate(self, bundle: ImportBundle) -> ValidationReport:
        if not bundle.source_artifacts:
            return ValidationReport(
                is_valid=False, errors=("No source artifacts in bundle",)
            )
        return ValidationReport(
            is_valid=True, warnings=(), qc_issues=bundle.qc_messages
        )


class FailingValidationAdapter(TestScientificAdapter):
    adapter_id = "fidelichem.failing_val"

    def probe(self, source: Path) -> DetectionReport:
        return DetectionReport(
            confidence=0.3,
            detected_format="failing_val",
            suggested_adapter=self.adapter_id,
        )

    def validate(self, bundle: ImportBundle) -> ValidationReport:

        return ValidationReport(
            is_valid=False,
            errors=("Data contains corrupted structure on line 12",),
        )


@pytest.fixture
def project_setup(tmp_path: Path):
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
    registry.register(TestScientificAdapter())
    registry.register(FailingValidationAdapter())

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
            Project(name="Demo Project", created_at=now, updated_at=now)
        )

    # Prepare mock input files on disk
    input_dir = tmp_path / "input_data"
    input_dir.mkdir()
    (input_dir / "compounds.csv").write_text(
        "id,smiles\nligand_001,CC(=O)Oc1ccccc1C(=O)O\n",
        encoding="utf-8",
    )
    (input_dir / "scores.csv").write_text(
        "id,score\nligand_001,75.5\n",
        encoding="utf-8",
    )

    try:
        yield manager, project.id, input_dir, _uow_factory
    finally:
        engine.dispose()


def test_import_manager_detect(project_setup) -> None:
    manager, project_id, input_dir, uow_factory = project_setup
    reports = manager.detect(input_dir)
    assert len(reports) >= 1
    assert reports[0].suggested_adapter == "fidelichem.test_sci"
    assert reports[0].confidence == 1.0


def test_import_manager_plan(project_setup) -> None:
    manager, project_id, input_dir, uow_factory = project_setup
    plan = manager.plan("fidelichem.test_sci", input_dir, options={"cutoff": 50})
    assert plan.adapter_id == "fidelichem.test_sci"
    assert "compounds.csv" in plan.source_files
    assert "scores.csv" in plan.source_files
    assert plan.options == {"cutoff": 50}


def test_import_manager_execute_import_happy_path(project_setup) -> None:
    manager, project_id, input_dir, uow_factory = project_setup
    plan = manager.plan("fidelichem.test_sci", input_dir)

    actor = IdentityActor(kind=ActorKind.USER, actor_id="scientist_1")
    result = manager.execute_import(project_id, plan, actor=actor)

    assert result.batch.status == ImportStatus.COMPLETED
    assert result.batch.project_id == project_id
    assert len(result.confirmed_resolutions) == 1

    # Verify database persistence
    with uow_factory() as uow:
        # Batch in DB
        batch_in_db = uow.import_batches.get(result.batch.id)
        assert batch_in_db is not None
        assert batch_in_db.status == ImportStatus.COMPLETED

        # Artifacts in DB
        artifacts = uow.source_artifacts.list_by_batch(result.batch.id)
        assert len(artifacts) == 2
        rel_paths = {a.relative_path for a in artifacts}
        assert rel_paths == {"compounds.csv", "scores.csv"}

        # Chemical entities in DB
        aliases = uow.aliases.list_by_batch(result.batch.id)
        assert len(aliases) == 1
        assert aliases[0].source_value == "ligand_001"

        # Scientific evidence is persisted with the same batch and remains
        # queryable after the import transaction closes.
        target_names = [
            target.name for target in uow.evidence.list_targets(result.batch.id)
        ]
        assert target_names == ["TargetAlpha"]
        assert len(uow.evidence.list_poses(result.batch.id)) == 1
        assert len(uow.evidence.list_scores(result.batch.id)) == 1
        assert (
            uow.evidence.list_docking_runs(result.batch.id)[0].engine
            == "UNSPECIFIED"
        )

        # Audit events in DB
        events = uow.audit_events.list_by_batch(result.batch.id)
        assert any(e.action == "import.completed" for e in events)


def test_import_manager_execute_duplicate_rejection(project_setup) -> None:
    manager, project_id, input_dir, uow_factory = project_setup
    plan = manager.plan("fidelichem.test_sci", input_dir)

    manager.execute_import(project_id, plan)

    # Second execution must raise DuplicateImportError
    with pytest.raises(DuplicateImportError, match="Duplicate import detected"):
        manager.execute_import(project_id, plan)


def test_import_manager_execute_validation_failure(project_setup) -> None:
    manager, project_id, input_dir, uow_factory = project_setup
    plan = manager.plan("fidelichem.failing_val", input_dir)

    with pytest.raises(ImportValidationError, match="corrupted structure"):
        manager.execute_import(project_id, plan)

    with uow_factory() as uow:
        batches = uow.import_batches.list_by_project(project_id)
        assert len(batches) == 0


def test_import_manager_dry_run(project_setup) -> None:
    manager, project_id, input_dir, uow_factory = project_setup
    plan = manager.plan("fidelichem.test_sci", input_dir)

    result = manager.execute_import(project_id, plan, dry_run=True)
    assert result.validation.is_valid
    assert len(result.bundle.compounds) == 1

    # In dry-run mode, no database entities are written
    with uow_factory() as uow:
        batches = uow.import_batches.list_by_project(project_id)
        assert len(batches) == 0


def test_import_manager_execute_failpoint_marks_batch_failed(project_setup) -> None:
    manager, project_id, input_dir, uow_factory = project_setup
    plan = manager.plan("fidelichem.test_sci", input_dir)

    def crashing_failpoint(point: str) -> None:
        if point == "before_batch_completion":
            raise RuntimeError("Simulated crash before completion")

    with pytest.raises(RuntimeError, match="Simulated crash"):
        manager.execute_import(project_id, plan, failpoint=crashing_failpoint)

    with uow_factory() as uow:
        batches = uow.import_batches.list_by_project(project_id)
        assert len(batches) == 1
        assert batches[0].status == ImportStatus.FAILED

        events = uow.audit_events.list_by_batch(batches[0].id)
        assert any(e.action == "import.failed" for e in events)


def test_import_manager_rollback_and_reimport(project_setup) -> None:
    manager, project_id, input_dir, uow_factory = project_setup
    plan = manager.plan("fidelichem.test_sci", input_dir)

    # 1. Execute initial import
    result = manager.execute_import(project_id, plan)
    assert result.batch.status == ImportStatus.COMPLETED

    # 2. Rollback the batch
    actor = IdentityActor(kind=ActorKind.USER, actor_id="lead_scientist")
    rolled_back = manager.rollback_import(
        project_id, result.batch.id, reason="Bad input parameter", actor=actor
    )
    assert rolled_back.status == ImportStatus.ROLLED_BACK
    assert rolled_back.rollback_reason == "Bad input parameter"

    with uow_factory() as uow:
        batch_db = uow.import_batches.get(result.batch.id)
        assert batch_db is not None
        assert batch_db.status == ImportStatus.ROLLED_BACK

        # Check rollback audit event
        events = uow.audit_events.list_by_batch(result.batch.id)
        assert any(e.action == "import.rolled_back" for e in events)

    # 3. Re-importing the identical plan must succeed now
    reimport_result = manager.execute_import(project_id, plan)
    assert reimport_result.batch.status == ImportStatus.COMPLETED
    assert reimport_result.batch.id != result.batch.id
