"""Safe creation and reopening of persistent FideliChem projects."""

from __future__ import annotations

import json
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError

from fidelichem.domain.json import canonical_json_bytes, canonicalize_json_text
from fidelichem.domain.models import Project
from fidelichem.storage.engine import create_sqlite_engine
from fidelichem.storage.runner import (
    MigrationError,
    assert_database_current,
    upgrade_database,
)
from fidelichem.storage.session import UnitOfWork

from .layout import ProjectPaths

Failpoint = Callable[[str], None]


class ProjectError(RuntimeError):
    """Base class for safe project layout errors."""


class ProjectConflictError(ProjectError):
    """The requested root already contains a project or user data."""


class ProjectManifestError(ProjectError):
    """The project manifest or corresponding database is invalid."""


class UnsafeManifestPathError(ProjectManifestError):
    """The manifest names a database outside the project root."""


_MANIFEST_KEYS = frozenset({"database", "name", "project_id", "schema_version"})


def create_project(
    root: str | Path,
    name: str,
    description: str | None = None,
    *,
    failpoint: Failpoint | None = None,
) -> ProjectPaths:
    """Create a migrated project, its manifest, and standard directories.

    Existing non-empty roots and known project files are never overwritten.
    On failure, only files and directories created by this invocation are
    removed; pre-existing user data is retained.
    """

    paths = ProjectPaths.for_root(Path(root))
    _refuse_conflict(paths)
    root_created = False
    created_directories: list[Path] = []
    engine: Engine | None = None
    manifest_created = False
    database_created = not paths.database.exists()
    try:
        if not paths.root.exists():
            try:
                paths.root.mkdir(parents=True)
            except FileExistsError:
                raise ProjectConflictError("project root already exists") from None
            root_created = True
        _trigger(failpoint, "after_root")
        for directory in paths.directories:
            if not directory.exists():
                directory.mkdir()
                created_directories.append(directory)
        _trigger(failpoint, "after_directories")

        engine = create_sqlite_engine(paths.database)
        upgrade_database(engine)
        _trigger(failpoint, "after_database")

        now = datetime.now(UTC)
        with UnitOfWork(engine) as uow:
            project = uow.projects.add(
                Project(
                    name=name,
                    description=description,
                    created_at=now,
                    updated_at=now,
                )
            )
        manifest = _manifest(project)
        _write_manifest(paths.manifest, manifest)
        manifest_created = True
        _trigger(failpoint, "after_manifest")
        return ProjectPaths.for_root(
            paths.root,
            project=project,
            engine=engine,
        )
    except (MigrationError, SQLAlchemyError):
        if engine is not None:
            engine.dispose()
        _cleanup_failed_creation(
            paths,
            root_created=root_created,
            created_directories=created_directories,
            database_created=database_created,
            manifest_created=manifest_created,
        )
        raise ProjectManifestError("project database could not be created") from None
    except BaseException:
        if engine is not None:
            engine.dispose()
        _cleanup_failed_creation(
            paths,
            root_created=root_created,
            created_directories=created_directories,
            database_created=database_created,
            manifest_created=manifest_created,
        )
        raise


def open_project(
    root: str | Path,
    read_only: bool = False,
) -> ProjectPaths:
    """Validate and open an existing project without changing its manifest."""

    paths = ProjectPaths.for_root(Path(root), read_only=read_only)
    if not paths.root.is_dir():
        raise ProjectManifestError("project root is unavailable")
    if any(not directory.is_dir() for directory in paths.directories):
        raise ProjectManifestError("project layout is incomplete")
    manifest = _read_manifest(paths.manifest)
    database_name = manifest["database"]
    database = _manifest_database_path(paths.root, database_name)
    if database != paths.database:
        paths = ProjectPaths(
            root=paths.root,
            manifest=paths.manifest,
            database=database,
            artifacts=paths.artifacts,
            cache=paths.cache,
            exports=paths.exports,
            logs=paths.logs,
            read_only=read_only,
        )
    if not database.is_file():
        raise ProjectManifestError("project database is unavailable")

    engine: Engine | None = None
    try:
        engine = create_sqlite_engine(database, read_only=read_only)
        if read_only:
            assert_database_current(engine)
        else:
            upgrade_database(engine)
        with UnitOfWork(engine) as uow:
            project = uow.projects.get()
        if project is None or not _manifest_matches(project, manifest):
            raise ProjectManifestError("project manifest does not match database")
        return ProjectPaths(
            root=paths.root,
            manifest=paths.manifest,
            database=database,
            artifacts=paths.artifacts,
            cache=paths.cache,
            exports=paths.exports,
            logs=paths.logs,
            project=project,
            engine=engine,
            read_only=read_only,
        )
    except ProjectError:
        if engine is not None:
            engine.dispose()
        raise
    except (MigrationError, OSError, SQLAlchemyError):
        if engine is not None:
            engine.dispose()
        raise ProjectManifestError("project database could not be opened") from None
    except BaseException:
        if engine is not None:
            engine.dispose()
        raise


def _refuse_conflict(paths: ProjectPaths) -> None:
    if not paths.root.exists():
        return
    if not paths.root.is_dir():
        raise ProjectConflictError("project root conflicts with an existing file")
    try:
        entries = tuple(paths.root.iterdir())
    except OSError:
        raise ProjectConflictError("project root is unavailable") from None
    if entries:
        raise ProjectConflictError("project root already contains data")


def _manifest(project: Project) -> dict[str, Any]:
    return {
        "database": "project.fidelichem.sqlite",
        "name": project.name,
        "project_id": project.id,
        "schema_version": project.schema_version,
    }


def _write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    created = False
    try:
        with path.open("xb") as stream:
            created = True
            stream.write(canonical_json_bytes(manifest))
    except FileExistsError:
        raise ProjectConflictError("project manifest already exists") from None
    except OSError:
        if created:
            _unlink_if_file(path)
        raise ProjectManifestError("project manifest could not be written") from None


def _read_manifest(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        decoded = raw.decode("utf-8")
        canonical = canonicalize_json_text(decoded)
        value = json.loads(canonical)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        raise ProjectManifestError("project manifest is invalid") from None
    if not isinstance(value, dict) or set(value) != _MANIFEST_KEYS:
        raise ProjectManifestError("project manifest is invalid")
    if decoded != canonical:
        raise ProjectManifestError("project manifest is not canonical")
    if not isinstance(value["database"], str):
        raise ProjectManifestError("project manifest is invalid")
    if not isinstance(value["name"], str):
        raise ProjectManifestError("project manifest is invalid")
    if not isinstance(value["project_id"], str):
        raise ProjectManifestError("project manifest is invalid")
    if not isinstance(value["schema_version"], int):
        raise ProjectManifestError("project manifest is invalid")
    return value


def _manifest_database_path(root: Path, value: str) -> Path:
    if (
        not value
        or "\x00" in value
        or "\\" in value
        or PurePosixPath(value).is_absolute()
        or Path(value).drive
    ):
        raise UnsafeManifestPathError("manifest database path is unsafe")
    parts = value.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise UnsafeManifestPathError("manifest database path is unsafe")
    candidate = (root / Path(*parts)).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        raise UnsafeManifestPathError("manifest database path is unsafe") from None
    return candidate


def _manifest_matches(project: Project, manifest: dict[str, Any]) -> bool:
    project_id = manifest["project_id"]
    name = manifest["name"]
    schema_version = manifest["schema_version"]
    return bool(
        isinstance(project_id, str)
        and isinstance(name, str)
        and isinstance(schema_version, int)
        and project.id == project_id
        and project.name == name
        and project.schema_version == schema_version
    )


def _trigger(failpoint: Failpoint | None, stage: str) -> None:
    if failpoint is not None:
        failpoint(stage)


def _cleanup_failed_creation(
    paths: ProjectPaths,
    *,
    root_created: bool,
    created_directories: list[Path],
    database_created: bool,
    manifest_created: bool,
) -> None:
    if manifest_created:
        _unlink_if_file(paths.manifest)
    if database_created:
        _unlink_if_file(paths.database)
    for directory in reversed(created_directories):
        _rmdir_if_empty(directory)
    if root_created:
        _rmdir_if_empty(paths.root)


def _unlink_if_file(path: Path) -> None:
    try:
        if path.is_file():
            path.unlink()
    except OSError:
        pass


def _rmdir_if_empty(path: Path) -> None:
    with suppress(OSError):
        path.rmdir()


__all__ = [
    "ProjectConflictError",
    "ProjectError",
    "ProjectManifestError",
    "UnsafeManifestPathError",
    "create_project",
    "open_project",
]
