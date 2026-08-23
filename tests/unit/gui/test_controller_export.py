"""Controller export tests using the persisted evidence read model."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from fidelichem.domain.adapters import DockingRunRecord, PoseRecord, TargetRecord
from fidelichem.domain.models import ImportBatch, ImportStatus
from fidelichem.exports.models import ExportFormat
from fidelichem.gui.controller import WorkspaceController
from fidelichem.projects.service import create_project
from fidelichem.storage.session import UnitOfWork

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def test_controller_exports_completed_persisted_evidence(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    paths = create_project(project_root, "GUI export")
    assert paths.engine is not None
    assert paths.project_id is not None

    batch = ImportBatch(
        project_id=paths.project_id,
        adapter_id="fixture",
        adapter_version="1.0",
        started_at=NOW,
        completed_at=NOW,
        status=ImportStatus.COMPLETED,
        source_root="inputs",
    )
    target = TargetRecord(name="Target A")
    run = DockingRunRecord(run_name="run-1", engine="fixture")
    pose = PoseRecord(
        run_name=run.run_name,
        compound_source_system="fixture",
        compound_source_value="lig-1",
        source_pose_id="pose-1",
        rank=1,
    )
    with UnitOfWork(paths.engine) as uow:
        uow.import_batches.add(batch)
        target_id = uow.evidence.add_target(target, import_batch_id=batch.id)
        run_id = uow.evidence.add_docking_run(
            run,
            import_batch_id=batch.id,
            target_id=target_id,
        )
        uow.evidence.add_pose(
            pose,
            import_batch_id=batch.id,
            docking_run_id=run_id,
        )
    paths.close()

    controller = WorkspaceController()
    controller.open_workspace(project_root)
    result = controller.export_project(
        tmp_path / "exports",
        formats=(ExportFormat.JSON,),
    )
    controller.close()

    exported = next(
        Path(path) for path in result.files if Path(path).suffix == ".json"
    )
    values = json.loads(exported.read_text(encoding="utf-8"))
    assert len(values) == 3
    assert {value["evidence_type"] for value in values} == {
        "target",
        "docking_run",
        "pose",
    }
    assert all(value["import_batch_id"] == batch.id for value in values)
