"""Immutable paths for the on-disk FideliChem project layout."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy import Engine

    from fidelichem.domain.models import Project


@dataclass(frozen=True, slots=True)
class ProjectPaths:
    """Absolute project paths and the optional opened project resources.

    Paths are immutable values.  When returned by :func:`create_project` or
    :func:`open_project`, ``project`` and ``engine`` contain the validated
    project row and its engine; those resources can be released with
    :meth:`close` without mutating this value.
    """

    root: Path
    manifest: Path
    database: Path
    artifacts: Path
    cache: Path
    exports: Path
    logs: Path
    project: Project | None = field(default=None, compare=False, repr=False)
    engine: Engine | None = field(default=None, compare=False, repr=False)
    read_only: bool = field(default=False, compare=False)

    @classmethod
    def for_root(
        cls,
        root: Path,
        *,
        project: Project | None = None,
        engine: Engine | None = None,
        read_only: bool = False,
    ) -> ProjectPaths:
        resolved = root.expanduser().resolve()
        return cls(
            root=resolved,
            manifest=resolved / "project.json",
            database=resolved / "project.fidelichem.sqlite",
            artifacts=resolved / "artifacts",
            cache=resolved / "cache",
            exports=resolved / "exports",
            logs=resolved / "logs",
            project=project,
            engine=engine,
            read_only=read_only,
        )

    @property
    def directories(self) -> tuple[Path, ...]:
        """Return the four standard project data directories in order."""

        return (self.artifacts, self.cache, self.exports, self.logs)

    @property
    def root_path(self) -> Path:
        return self.root

    @property
    def manifest_path(self) -> Path:
        return self.manifest

    @property
    def project_json(self) -> Path:
        return self.manifest

    @property
    def database_path(self) -> Path:
        return self.database

    @property
    def artifacts_dir(self) -> Path:
        return self.artifacts

    @property
    def cache_dir(self) -> Path:
        return self.cache

    @property
    def exports_dir(self) -> Path:
        return self.exports

    @property
    def logs_dir(self) -> Path:
        return self.logs

    @property
    def project_id(self) -> str | None:
        return None if self.project is None else self.project.id

    def close(self) -> None:
        """Release the SQLAlchemy engine associated with this opened project."""

        if self.engine is not None:
            self.engine.dispose()

    def __enter__(self) -> ProjectPaths:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
