"""Universal adapter protocol and base ingestion utilities."""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from fidelichem.domain.adapters import (
    DetectionReport,
    ImportBundle,
    ImportPlan,
    SourceArtifactRecord,
    ValidationReport,
    compute_plan_hash,
)
from fidelichem.provenance.hashing import sha256_file


@runtime_checkable
class EvidenceAdapter(Protocol):
    """Universal contract that every scientific evidence producer must implement."""

    adapter_id: str
    adapter_version: str
    display_name: str

    def probe(self, source: Path) -> DetectionReport:
        """Inspect a file or directory and report detection confidence and format."""
        ...

    def plan(
        self, source: Path, options: Mapping[str, Any] | None = None
    ) -> ImportPlan:
        """Construct an immutable, hashed plan from the inspected source."""
        ...

    def parse(self, plan: ImportPlan) -> ImportBundle:
        """Parse source artifacts into a canonical, storage-agnostic evidence bundle."""
        ...

    def validate(self, bundle: ImportBundle) -> ValidationReport:
        """Perform semantic and quality control validation on the canonical bundle."""
        ...


def scan_source_files(
    source_root: Path,
    patterns: tuple[str, ...] = ("*",),
    *,
    include_hidden: bool = False,
) -> tuple[Path, ...]:
    """Discover candidate source files relative to source_root matching patterns."""
    root = source_root.resolve()
    if not root.exists():
        return ()

    if root.is_file():
        return (Path(root.name),)

    found_paths: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        if not include_hidden:
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        curr_dir = Path(dirpath)
        for filename in filenames:
            if not include_hidden and filename.startswith("."):
                continue
            full_path = curr_dir / filename
            rel_path = full_path.relative_to(root)
            for pattern in patterns:
                if rel_path.match(pattern):
                    found_paths.append(rel_path)
                    break

    return tuple(sorted(found_paths, key=lambda p: p.as_posix()))


def compute_source_artifacts(
    source_root: Path,
    relative_paths: Sequence[Path | str],
) -> tuple[SourceArtifactRecord, ...]:
    """Compute cryptographic hashes and file metadata for relative source paths."""
    root = source_root.resolve()
    # Plans use paths relative to a directory even when the user selected one
    # individual file.  Keeping that invariant lets every adapter parse a
    # selected CSV/XLSX/MOL2 without special-casing ``file / filename``.
    base_root = root.parent if root.is_file() else root
    artifacts: list[SourceArtifactRecord] = []

    for item in relative_paths:
        rel_posix = Path(item).as_posix()
        full_path = base_root / rel_posix
        if not full_path.is_file():
            raise ValueError(f"Source file does not exist: {full_path}")

        sha = sha256_file(full_path)
        stat = full_path.stat()
        mtime = datetime.fromtimestamp(stat.st_mtime, tz=UTC)
        file_type = full_path.suffix.lstrip(".").lower() or "bin"

        artifacts.append(
            SourceArtifactRecord(
                relative_path=rel_posix,
                sha256=sha,
                size_bytes=stat.st_size,
                file_type=file_type,
                mtime=mtime,
            )
        )

    return tuple(sorted(artifacts, key=lambda a: a.relative_path))


def verify_import_plan(plan: ImportPlan) -> None:
    """Verify that every source still matches the immutable import plan.

    Planning is deliberately separate from parsing so a user can review a
    plan before importing.  Re-hashing at the parse boundary prevents a file
    changed in that interval from being parsed under stale provenance.
    """
    expected = dict(plan.file_hashes)
    if set(expected) != set(plan.source_files):
        raise ValueError("Import plan source files and hashes do not match")

    actual = compute_source_artifacts(Path(plan.source_root), plan.source_files)
    actual_hashes = {artifact.relative_path: artifact.sha256 for artifact in actual}
    mismatches = [
        rel_path
        for rel_path in plan.source_files
        if actual_hashes.get(rel_path) != expected.get(rel_path)
    ]
    if mismatches:
        paths = ", ".join(sorted(mismatches))
        raise ValueError(
            f"Import plan is stale; source content changed since planning: {paths}"
        )


def build_import_plan(
    adapter_id: str,
    adapter_version: str,
    source_root: str,
    artifacts: Sequence[SourceArtifactRecord],
    options: Mapping[str, Any] | None = None,
    created_at: datetime | None = None,
) -> ImportPlan:
    """Helper to assemble a validated, content-hashed ImportPlan."""
    opt_map = dict(options or {})
    declared_root = Path(source_root)
    plan_root = (
        declared_root.parent
        if declared_root.exists() and declared_root.is_file()
        else declared_root
    )
    source_files = tuple(a.relative_path for a in artifacts)
    file_hashes = tuple((a.relative_path, a.sha256) for a in artifacts)
    ts = created_at or datetime.now(UTC)

    plan_hash = compute_plan_hash(
        adapter_id=adapter_id,
        adapter_version=adapter_version,
        source_root=str(plan_root),
        source_files=source_files,
        file_hashes=file_hashes,
        options=opt_map,
    )

    return ImportPlan(
        adapter_id=adapter_id,
        adapter_version=adapter_version,
        source_root=str(plan_root),
        source_files=source_files,
        file_hashes=file_hashes,
        options=opt_map,
        created_at=ts,
        plan_hash=plan_hash,
    )


__all__ = [
    "EvidenceAdapter",
    "build_import_plan",
    "compute_source_artifacts",
    "scan_source_files",
    "verify_import_plan",
]
