"""Unit tests for EvidenceAdapter protocol and base adapter utilities."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fidelichem.adapters.base import (
    EvidenceAdapter,
    build_import_plan,
    compute_source_artifacts,
    scan_source_files,
)
from fidelichem.domain.adapters import (
    DetectionReport,
    ImportBundle,
    ImportPlan,
    ValidationReport,
)


class DummyAdapter:
    adapter_id = "fidelichem.dummy"
    adapter_version = "0.1.0"
    display_name = "Dummy Test Adapter"

    def probe(self, source: Path) -> DetectionReport:
        return DetectionReport(
            confidence=0.8,
            detected_format="dummy_txt",
            suggested_adapter=self.adapter_id,
        )

    def plan(
        self, source: Path, options: Mapping[str, Any] | None = None
    ) -> ImportPlan:
        artifacts = compute_source_artifacts(source, ["dummy.txt"])
        return build_import_plan(
            adapter_id=self.adapter_id,
            adapter_version=self.adapter_version,
            source_root=str(source),
            artifacts=artifacts,
            options=options,
        )

    def parse(self, plan: ImportPlan) -> ImportBundle:
        return ImportBundle(plan=plan)

    def validate(self, bundle: ImportBundle) -> ValidationReport:
        return ValidationReport(is_valid=True)


def test_evidence_adapter_protocol_compliance() -> None:
    adapter = DummyAdapter()
    assert isinstance(adapter, EvidenceAdapter)
    assert adapter.adapter_id == "fidelichem.dummy"
    assert adapter.display_name == "Dummy Test Adapter"


def test_scan_source_files_finds_files(tmp_path: Path) -> None:
    f1 = tmp_path / "sub1" / "fileA.txt"
    f2 = tmp_path / "sub2" / "fileB.mol2"
    f_hidden = tmp_path / ".hidden" / "ignored.txt"
    f1.parent.mkdir(parents=True)
    f2.parent.mkdir(parents=True)
    f_hidden.parent.mkdir(parents=True)
    f1.write_text("hello A", encoding="utf-8")
    f2.write_text("hello B", encoding="utf-8")
    f_hidden.write_text("secret", encoding="utf-8")

    files = scan_source_files(tmp_path)
    posix_files = {p.as_posix() for p in files}
    assert "sub1/fileA.txt" in posix_files
    assert "sub2/fileB.mol2" in posix_files
    assert not any(".hidden" in str(p) for p in files)


def test_compute_source_artifacts(tmp_path: Path) -> None:
    file_path = tmp_path / "data.csv"
    content = b"col1,col2\nval1,val2\n"
    file_path.write_bytes(content)

    artifacts = compute_source_artifacts(tmp_path, ["data.csv"])
    assert len(artifacts) == 1
    art = artifacts[0]
    assert art.relative_path == "data.csv"
    assert art.size_bytes == len(content)
    assert len(art.sha256) == 64
    assert art.file_type == "csv"
    assert art.mtime is not None


def test_build_import_plan(tmp_path: Path) -> None:
    file_path = tmp_path / "scores.lst"
    file_path.write_text("score 42\n", encoding="utf-8")

    artifacts = compute_source_artifacts(tmp_path, ["scores.lst"])
    clock_now = datetime(2026, 8, 22, 14, 0, 0, tzinfo=UTC)

    plan = build_import_plan(
        adapter_id="fidelichem.dummy",
        adapter_version="0.1.0",
        source_root=str(tmp_path),
        artifacts=artifacts,
        options={"header": True},
        created_at=clock_now,
    )
    assert plan.adapter_id == "fidelichem.dummy"
    assert plan.source_files == ("scores.lst",)
    assert len(plan.file_hashes) == 1
    assert plan.file_hashes[0][0] == "scores.lst"
    assert plan.options == {"header": True}
    assert plan.created_at == clock_now
    assert len(plan.plan_hash) == 64
