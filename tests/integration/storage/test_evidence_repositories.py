from __future__ import annotations

from datetime import UTC, datetime

import pytest

from fidelichem.domain.adapters import (
    DockingRunRecord,
    InteractionRecord,
    MDMetricRecord,
    MDRunRecord,
    PoseRecord,
    ScoreObservationRecord,
    TargetRecord,
)
from fidelichem.domain.models import ImportBatch, Project, SourceArtifact
from fidelichem.storage.repositories import ForeignKeyViolationError
from fidelichem.storage.session import UnitOfWork

NOW = datetime(2026, 1, 1, tzinfo=UTC)
HASH = "a" * 64


def _seed(migrated_engine: object) -> tuple[Project, ImportBatch, SourceArtifact]:
    project = Project(
        id="11111111-1111-4111-8111-111111111111",
        name="Evidence",
        created_at=NOW,
        updated_at=NOW,
    )
    batch = ImportBatch(
        id="22222222-2222-4222-8222-222222222222",
        project_id=project.id,
        adapter_id="gold",
        adapter_version="1.0",
        started_at=NOW,
        source_root="inputs",
    )
    artifact = SourceArtifact(
        id="33333333-3333-4333-8333-333333333333",
        import_batch_id=batch.id,
        path="inputs/results.dat",
        relative_path="results.dat",
        sha256=HASH,
        file_type="dat",
        size_bytes=10,
        mtime=NOW,
    )
    with UnitOfWork(migrated_engine) as uow:
        uow.projects.add(project)
        uow.import_batches.add(batch)
        uow.source_artifacts.add(artifact)
    return project, batch, artifact


def test_evidence_repository_persists_complete_bundle_with_provenance(
    migrated_engine: object,
) -> None:
    _, batch, artifact = _seed(migrated_engine)
    target = TargetRecord(name="Target A", pdb_id="1ABC", chain="A")
    run = DockingRunRecord(run_name="run-1", target_name=target.name, engine="gold")
    pose = PoseRecord(
        run_name=run.run_name,
        compound_source_system="gold",
        compound_source_value="lig-1",
        source_pose_id="pose-1",
        rank=1,
        structure_artifact_path="poses/pose-1.sdf",
    )
    score = ScoreObservationRecord(
        run_name=run.run_name,
        compound_source_value="lig-1",
        source_pose_id=pose.source_pose_id,
        score_key="fitness",
        raw_value=-7.2,
        source_artifact_path="results.dat",
    )
    interaction = InteractionRecord(
        run_name=run.run_name,
        compound_source_value="lig-1",
        source_pose_id=pose.source_pose_id,
        residue_name="SER70",
        interaction_type="hydrogen_bond",
        target_name=target.name,
        distance=2.8,
    )
    md_run = MDRunRecord(
        run_name="md-1",
        target_name=target.name,
        compound_source_value="lig-1",
        source_pose_id=pose.source_pose_id,
        duration_ns=10.0,
    )
    metric = MDMetricRecord(
        run_name=md_run.run_name,
        metric_key="rmsd",
        unit="nm",
        mean_value=0.2,
        time_points=(0.0, 1.0),
        values=(0.1, 0.3),
        source_artifact_path="results.dat",
    )

    with UnitOfWork(migrated_engine) as uow:
        target_id = uow.evidence.add_target(
            target, import_batch_id=batch.id, source_artifact_id=artifact.id
        )
        run_id = uow.evidence.add_docking_run(
            run,
            import_batch_id=batch.id,
            target_id=target_id,
            source_artifact_id=artifact.id,
        )
        pose_id = uow.evidence.add_pose(
            pose,
            import_batch_id=batch.id,
            docking_run_id=run_id,
            source_artifact_id=artifact.id,
        )
        uow.evidence.add_score(
            score,
            import_batch_id=batch.id,
            docking_run_id=run_id,
            pose_id=pose_id,
            source_artifact_id=artifact.id,
        )
        uow.evidence.add_interaction(
            interaction,
            import_batch_id=batch.id,
            docking_run_id=run_id,
            pose_id=pose_id,
            target_id=target_id,
            source_artifact_id=artifact.id,
        )
        md_run_id = uow.evidence.add_md_run(
            md_run,
            import_batch_id=batch.id,
            target_id=target_id,
            pose_id=pose_id,
            source_artifact_id=artifact.id,
        )
        uow.evidence.add_md_metric(
            metric,
            import_batch_id=batch.id,
            md_run_id=md_run_id,
            source_artifact_id=artifact.id,
        )

    with UnitOfWork(migrated_engine) as uow:
        assert uow.evidence.list_targets(batch.id) == (target,)
        assert uow.evidence.list_docking_runs(batch.id) == (run,)
        assert uow.evidence.list_poses(batch.id) == (pose,)
        assert uow.evidence.list_scores(batch.id) == (score,)
        assert uow.evidence.list_interactions(batch.id) == (interaction,)
        assert uow.evidence.list_md_runs(batch.id) == (md_run,)
        assert uow.evidence.list_md_metrics(batch.id) == (metric,)

    with UnitOfWork(migrated_engine) as uow:
        uow.import_batches.complete(batch.id)

    with UnitOfWork(migrated_engine) as uow:
        records = uow.evidence.list_export_records(project_id=batch.project_id)

    assert len(records) == 7
    assert [record["evidence_type"] for record in records] == [
        "target",
        "docking_run",
        "pose",
        "score",
        "interaction",
        "md_run",
        "md_metric",
    ]
    assert all(record["import_batch_id"] == batch.id for record in records)
    assert records[2]["source_pose_id"] == pose.source_pose_id

    with UnitOfWork(migrated_engine) as uow:
        filtered = uow.evidence.list_export_records(
            project_id=batch.project_id,
            include_scores=False,
            include_interactions=False,
            include_dynamics=False,
            include_provenance=False,
        )

    assert [record["evidence_type"] for record in filtered] == [
        "target",
        "docking_run",
        "pose",
    ]
    assert all("import_batch_id" not in record for record in filtered)


def test_evidence_repository_requires_parent_and_is_append_only(
    migrated_engine: object,
) -> None:
    _, batch, _ = _seed(migrated_engine)
    target = TargetRecord(name="Target A")
    with pytest.raises(ForeignKeyViolationError), UnitOfWork(migrated_engine) as uow:
        uow.evidence.add_target(
            target,
            import_batch_id="44444444-4444-4444-8444-444444444444",
        )

    with UnitOfWork(migrated_engine) as uow:
        target_id = uow.evidence.add_target(target, import_batch_id=batch.id)
        assert target_id
        with pytest.raises(AttributeError):
            uow.evidence.update_target(target_id, target)
