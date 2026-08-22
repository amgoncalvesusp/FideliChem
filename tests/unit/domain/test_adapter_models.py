"""Unit tests for Phase 3 adapter domain models and bundles."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from fidelichem.domain.adapters import (
    DetectionReport,
    DockingRunRecord,
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
    compute_plan_hash,
)
from fidelichem.domain.errors import (
    AdapterExecutionError,
    AdapterNotFoundError,
    DuplicateImportError,
    ImportValidationError,
)


def test_detection_report_valid_and_frozen() -> None:

    report = DetectionReport(
        confidence=0.95,
        detected_format="gold_docking_dir",
        candidate_files=("gold.conf", "bestranking.lst"),
        warnings=("missing receptor pdb",),
        requires_user_mapping=False,
        suggested_adapter="fidelichem.gold",
        extra_metadata={"preset": "default"},
    )
    assert report.confidence == 0.95
    assert report.detected_format == "gold_docking_dir"
    assert report.candidate_files == ("gold.conf", "bestranking.lst")
    assert report.warnings == ("missing receptor pdb",)
    assert report.requires_user_mapping is False
    assert report.suggested_adapter == "fidelichem.gold"
    assert report.extra_metadata == {"preset": "default"}

    with pytest.raises(ValidationError):
        report.confidence = 0.5  # type: ignore[misc]


def test_detection_report_confidence_bounds() -> None:
    with pytest.raises(ValidationError, match="confidence"):
        DetectionReport(
            confidence=-0.1,
            detected_format="fmt",
            suggested_adapter="adapter",
        )

    with pytest.raises(ValidationError, match="confidence"):
        DetectionReport(
            confidence=1.1,
            detected_format="fmt",
            suggested_adapter="adapter",
        )


def test_import_plan_creation_and_deterministic_hash() -> None:
    now = datetime(2026, 8, 22, 12, 0, 0, tzinfo=UTC)
    sha1 = "a" * 64
    sha2 = "b" * 64
    plan_hash = compute_plan_hash(
        adapter_id="fidelichem.fake",
        adapter_version="0.1.0",
        source_root="/data/docking",
        source_files=("input.csv", "scores.csv"),
        file_hashes=(("input.csv", sha1), ("scores.csv", sha2)),
        options={"score_column": "ChemPLP"},
    )
    plan = ImportPlan(
        adapter_id="fidelichem.fake",
        adapter_version="0.1.0",
        source_root="/data/docking",
        source_files=("input.csv", "scores.csv"),
        file_hashes=(("input.csv", sha1), ("scores.csv", sha2)),
        options={"score_column": "ChemPLP"},
        created_at=now,
        plan_hash=plan_hash,
    )
    assert plan.adapter_id == "fidelichem.fake"
    assert plan.plan_hash == plan_hash
    assert len(plan.plan_hash) == 64

    # Hash changes when options change
    other_hash = compute_plan_hash(
        adapter_id="fidelichem.fake",
        adapter_version="0.1.0",
        source_root="/data/docking",
        source_files=("input.csv", "scores.csv"),
        file_hashes=(("input.csv", sha1), ("scores.csv", sha2)),
        options={"score_column": "GoldScore"},
    )
    assert other_hash != plan_hash


def test_import_plan_rejects_naive_timestamp() -> None:
    sha = "c" * 64
    with pytest.raises(ValidationError, match="timestamp must be timezone-aware"):
        ImportPlan(
            adapter_id="fidelichem.fake",
            adapter_version="0.1.0",
            source_root="/data",
            source_files=("file.txt",),
            file_hashes=(("file.txt", sha),),
            created_at=datetime(2026, 8, 22, 12, 0, 0),  # Naive
            plan_hash=sha,
        )


def test_qc_issue_and_validation_report() -> None:
    issue_warn = QCIssue(
        code="QC_MISSING_OPTIONAL_COLUMN",
        message="Column 'Notes' was not found",
        severity=QCSeverity.WARNING,
        source_file="table.csv",
        line_number=1,
    )
    issue_err = QCIssue(
        code="QC_INVALID_SMILES",
        message="SMILES could not be parsed",
        severity=QCSeverity.ERROR,
        source_file="table.csv",
        line_number=42,
        entity_reference="CMPD_001",
    )
    val_report = ValidationReport(
        is_valid=False,
        errors=("SMILES could not be parsed at line 42",),
        warnings=("Column 'Notes' was not found",),
        qc_issues=(issue_warn, issue_err),
    )
    assert not val_report.is_valid
    assert len(val_report.errors) == 1
    assert len(val_report.warnings) == 1
    assert len(val_report.qc_issues) == 2


def test_raw_compound_record_validation() -> None:
    compound = RawCompoundRecord(
        source_system="gold",
        source_value="ligand_457",
        source_smiles="CC(=O)Oc1ccccc1C(=O)O",
        source_inchikey="BSYNRYMUTXBXSQ-UHFFFAOYSA-N",
        preparation_ph=7.4,
        source_artifact_path="solutions.mol2",
    )
    assert compound.source_system == "gold"
    assert compound.source_value == "ligand_457"
    assert compound.preparation_ph == 7.4

    with pytest.raises(ValidationError, match="source_system"):
        RawCompoundRecord(source_system="   ", source_value="ligand_1")

    with pytest.raises(ValidationError, match="source_value"):
        RawCompoundRecord(source_system="gold", source_value="")


def test_pose_and_score_observation_records() -> None:
    pose = PoseRecord(
        run_name="Run_01",
        compound_source_system="gold",
        compound_source_value="ligand_457",
        source_pose_id="P001",
        rank=1,
        structure_artifact_path="gold_soln_1.mol2",
        coordinate_hash="d" * 64,
    )
    assert pose.rank == 1

    with pytest.raises(ValidationError, match="rank"):
        PoseRecord(
            run_name="Run_01",
            compound_source_system="gold",
            compound_source_value="ligand_457",
            source_pose_id="P001",
            rank=0,  # Rank must be >= 1
        )

    score = ScoreObservationRecord(
        run_name="Run_01",
        compound_source_value="ligand_457",
        source_pose_id="P001",
        score_key="gold.chemplp",
        raw_value=86.4,
        source_artifact_path="bestranking.lst",
    )
    assert score.raw_value == 86.4

    with pytest.raises(ValidationError, match="raw_value"):
        ScoreObservationRecord(
            run_name="Run_01",
            compound_source_value="ligand_457",
            source_pose_id="P001",
            score_key="gold.chemplp",
            raw_value=float("nan"),  # Non-finite rejected
        )


def test_import_bundle_assembly() -> None:
    now = datetime(2026, 8, 22, 12, 0, 0, tzinfo=UTC)
    sha = "e" * 64
    plan = ImportPlan(
        adapter_id="fidelichem.fake",
        adapter_version="0.1.0",
        source_root="/data",
        source_files=("input.csv",),
        file_hashes=(("input.csv", sha),),
        created_at=now,
        plan_hash=sha,
    )
    artifact = SourceArtifactRecord(
        relative_path="input.csv",
        sha256=sha,
        size_bytes=1024,
        file_type="csv",
        mtime=now,
    )
    compound = RawCompoundRecord(
        source_system="test",
        source_value="CMPD1",
        source_smiles="CCO",
    )
    target = TargetRecord(name="CTX-M-15", pdb_id="1IYS")
    run = DockingRunRecord(run_name="Run_01", target_name="CTX-M-15", engine="GOLD")
    pose = PoseRecord(
        run_name="Run_01",
        compound_source_system="test",
        compound_source_value="CMPD1",
        source_pose_id="1",
        rank=1,
    )
    score = ScoreObservationRecord(
        run_name="Run_01",
        compound_source_value="CMPD1",
        source_pose_id="1",
        score_key="test.score",
        raw_value=42.0,
    )

    bundle = ImportBundle(
        plan=plan,
        targets=(target,),
        compounds=(compound,),
        docking_runs=(run,),
        poses=(pose,),
        scores=(score,),
        source_artifacts=(artifact,),
        qc_messages=(),
        provenance={"generator": "test_suite"},
    )
    assert len(bundle.targets) == 1
    assert len(bundle.compounds) == 1
    assert len(bundle.docking_runs) == 1
    assert len(bundle.poses) == 1
    assert len(bundle.scores) == 1
    assert len(bundle.source_artifacts) == 1
    assert bundle.provenance == {"generator": "test_suite"}


def test_typed_adapter_errors() -> None:
    dup_err = DuplicateImportError("Batch already imported with same input hash")
    assert isinstance(dup_err, ValueError)
    assert "Batch already imported" in str(dup_err)

    val_err = ImportValidationError("Validation failed with 2 errors")
    assert isinstance(val_err, ValueError)

    not_found = AdapterNotFoundError("Adapter 'gold' not registered")
    assert isinstance(not_found, ValueError)

    exec_err = AdapterExecutionError("Adapter parsing crashed on corrupted input")
    assert isinstance(exec_err, ValueError)
