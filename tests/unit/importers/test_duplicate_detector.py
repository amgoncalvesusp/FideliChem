"""Unit tests for DuplicateImportDetector."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine

from fidelichem.domain.adapters import ImportPlan, compute_plan_hash
from fidelichem.domain.errors import DuplicateImportError
from fidelichem.domain.models import (
    ImportBatch,
    Project,
    SourceArtifact,
)
from fidelichem.importers.duplicate_detector import DuplicateImportDetector
from fidelichem.storage.orm import Base
from fidelichem.storage.session import UnitOfWork


@pytest.fixture
def uow_factory(tmp_path: Path):
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)

    def _factory() -> UnitOfWork:
        return UnitOfWork(engine)

    return _factory


def test_duplicate_detector_finds_completed_batch_with_same_input_hash(
    uow_factory,
) -> None:
    detector = DuplicateImportDetector()
    now = datetime(2026, 8, 22, 12, 0, 0, tzinfo=UTC)
    sha1 = "1" * 64

    with uow_factory() as uow:
        project = uow.projects.add(
            Project(name="Test Project", created_at=now, updated_at=now)
        )
        batch = uow.import_batches.add(
            ImportBatch(
                project_id=project.id,
                adapter_id="fidelichem.fake",
                adapter_version="0.1.0",
                started_at=now,
                source_root="/data",
                input_hash=sha1,
            )
        )
        uow.import_batches.complete(batch.id, completed_at=now)

    plan = ImportPlan(
        adapter_id="fidelichem.fake",
        adapter_version="0.1.0",
        source_root="/data",
        source_files=("file.csv",),
        file_hashes=(("file.csv", sha1),),
        created_at=now,
        plan_hash=sha1,
    )

    with uow_factory() as uow:
        dup = detector.check_duplicate(uow, project.id, plan)
        assert dup is not None
        assert dup.id == batch.id

        with pytest.raises(DuplicateImportError, match="Duplicate import detected"):
            detector.assert_not_duplicate(uow, project.id, plan)


def test_duplicate_detector_ignores_failed_or_rolled_back_batches(
    uow_factory,
) -> None:
    detector = DuplicateImportDetector()
    now = datetime(2026, 8, 22, 12, 0, 0, tzinfo=UTC)
    sha1 = "2" * 64

    with uow_factory() as uow:
        project = uow.projects.add(
            Project(name="Test Project", created_at=now, updated_at=now)
        )
        batch_failed = uow.import_batches.add(
            ImportBatch(
                project_id=project.id,
                adapter_id="fidelichem.fake",
                adapter_version="0.1.0",
                started_at=now,
                source_root="/data",
                input_hash=sha1,
            )
        )
        uow.import_batches.fail(batch_failed.id, completed_at=now)

    plan = ImportPlan(
        adapter_id="fidelichem.fake",
        adapter_version="0.1.0",
        source_root="/data",
        source_files=("file.csv",),
        file_hashes=(("file.csv", sha1),),
        created_at=now,
        plan_hash=sha1,
    )

    with uow_factory() as uow:
        dup = detector.check_duplicate(uow, project.id, plan)
        assert dup is None
        # Should not raise
        detector.assert_not_duplicate(uow, project.id, plan)


def test_duplicate_detector_matches_identical_artifact_set(
    uow_factory,
) -> None:
    detector = DuplicateImportDetector()
    now = datetime(2026, 8, 22, 12, 0, 0, tzinfo=UTC)
    sha_a = "a" * 64
    sha_b = "b" * 64

    with uow_factory() as uow:
        project = uow.projects.add(
            Project(name="Test Project", created_at=now, updated_at=now)
        )
        batch = uow.import_batches.add(
            ImportBatch(
                project_id=project.id,
                adapter_id="fidelichem.fake",
                adapter_version="0.1.0",
                started_at=now,
                source_root="/data",
                file_count=2,
                input_hash="f" * 64,
            )
        )
        uow.source_artifacts.add(
            SourceArtifact(
                import_batch_id=batch.id,
                path="/data/file1.csv",
                relative_path="file1.csv",
                sha256=sha_a,
                file_type="csv",
                size_bytes=100,
                mtime=now,
            )
        )
        uow.source_artifacts.add(
            SourceArtifact(
                import_batch_id=batch.id,
                path="/data/file2.csv",
                relative_path="file2.csv",
                sha256=sha_b,
                file_type="csv",
                size_bytes=200,
                mtime=now,
            )
        )
        uow.import_batches.complete(batch.id, completed_at=now)

    plan_hash = compute_plan_hash(
        "fidelichem.fake",
        "0.1.0",
        "/data",
        ("file1.csv", "file2.csv"),
        (("file1.csv", sha_a), ("file2.csv", sha_b)),
        {},
    )
    plan = ImportPlan(
        adapter_id="fidelichem.fake",
        adapter_version="0.1.0",
        source_root="/data",
        source_files=("file1.csv", "file2.csv"),
        file_hashes=(("file1.csv", sha_a), ("file2.csv", sha_b)),
        options={},
        created_at=now,
        plan_hash=plan_hash,
    )

    with uow_factory() as uow:
        dup = detector.check_duplicate(uow, project.id, plan)
        assert dup is not None
        assert dup.id == batch.id
