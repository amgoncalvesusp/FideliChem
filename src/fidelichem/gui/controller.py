"""Application-facing orchestration for the desktop GUI.

Views emit intent only.  This controller composes the existing project,
adapter, import, and export services so widgets never contain SQL or
scientific decision rules.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fidelichem.adapters.registry import AdapterRegistry
from fidelichem.chemistry.service import ChemistryService
from fidelichem.domain.adapters import DetectionReport, ImportResult
from fidelichem.domain.chemistry import IdentityActor
from fidelichem.domain.models import ActorKind
from fidelichem.exports.engine import ExportEngine
from fidelichem.exports.models import ExportFormat, ExportOptions, ExportResult
from fidelichem.identity.service import IdentityService
from fidelichem.importers.manager import ImportManager
from fidelichem.projects.layout import ProjectPaths
from fidelichem.projects.service import create_project, open_project
from fidelichem.storage.identity_index import PersistentIdentityIndex
from fidelichem.storage.session import UnitOfWork


@dataclass(frozen=True, slots=True)
class WorkspaceState:
    """Serializable view state for the currently opened project."""

    name: str
    root: Path
    project_id: str


class WorkspaceController:
    """Compose application services for user intents coming from the GUI."""

    def __init__(self, registry: AdapterRegistry | None = None) -> None:
        self._registry = registry or AdapterRegistry.with_builtins()
        self._paths: ProjectPaths | None = None

    @property
    def state(self) -> WorkspaceState | None:
        paths = self._paths
        if paths is None or paths.project is None:
            return None
        return WorkspaceState(
            name=paths.project.name,
            root=paths.root,
            project_id=paths.project.id,
        )

    def create_workspace(self, name: str, root: str | Path) -> WorkspaceState:
        clean_name = name.strip()
        clean_root = str(root).strip()
        if not clean_name or not clean_root:
            raise ValueError("Project name and workspace path are required")
        paths = create_project(Path(clean_root), clean_name)
        self._replace_paths(paths)
        state = self.state
        if state is None:  # pragma: no cover - project service guarantees this
            raise RuntimeError("created workspace has no project identity")
        return state

    def open_workspace(self, root: str | Path) -> WorkspaceState:
        clean_root = str(root).strip()
        if not clean_root:
            raise ValueError("Workspace path is required")
        paths = open_project(Path(clean_root))
        self._replace_paths(paths)
        state = self.state
        if state is None:  # pragma: no cover - project service guarantees this
            raise RuntimeError("opened workspace has no project identity")
        return state

    def probe(self, adapter_id: str, source: str | Path) -> tuple[DetectionReport, ...]:
        source_path = self._require_source(source)
        if adapter_id == "auto":
            return self._registry.probe_all(source_path)
        return (self._registry.get(adapter_id).probe(source_path),)

    def import_evidence(
        self,
        adapter_id: str,
        source: str | Path,
        *,
        options: Mapping[str, Any] | None = None,
    ) -> ImportResult:
        paths = self._require_workspace()
        source_path = self._require_source(source)
        manager = self._import_manager(paths)
        plan = manager.plan(adapter_id, source_path, options)
        actor = IdentityActor(kind=ActorKind.USER, actor_id="gui")
        return manager.execute_import(paths.project_id or "", plan, actor=actor)

    def export_project(
        self,
        destination: str | Path,
        *,
        formats: tuple[ExportFormat, ...],
        records: tuple[Mapping[str, Any], ...] | None = None,
        options: ExportOptions | None = None,
    ) -> ExportResult:
        """Export a persisted evidence snapshot through :class:`ExportEngine`.

        Callers may provide a previously prepared snapshot for specialized
        workflows.  The normal GUI path loads a fresh snapshot from the
        storage read model and never queries SQL from a widget.
        """

        state = self.state
        if state is None:
            raise ValueError("Open a workspace before exporting")
        export_options = options or ExportOptions(formats=formats)
        if records is None:
            records = self._load_export_records(state.project_id, export_options)
        if not records:
            raise ValueError("The workspace has no completed scientific evidence")
        destination_value = str(destination).strip()
        paths = self._require_workspace()
        target = Path(destination_value) if destination_value else paths.exports
        return ExportEngine().export_dataset(
            project_name=state.name,
            records=records,
            output_dir=target,
            options=export_options,
            parameters={"project_id": state.project_id},
        )

    def _load_export_records(
        self,
        project_id: str,
        options: ExportOptions,
    ) -> tuple[Mapping[str, Any], ...]:
        paths = self._paths
        if paths is None or paths.engine is None:
            raise ValueError("Open a workspace before exporting")
        with UnitOfWork(paths.engine) as uow:
            return uow.evidence.list_export_records(
                project_id,
                include_scores=options.include_scores,
                include_interactions=options.include_interactions,
                include_dynamics=options.include_dynamics,
                include_provenance=options.include_provenance,
            )

    def close(self) -> None:
        paths = self._paths
        self._paths = None
        if paths is not None:
            paths.close()

    def _import_manager(self, paths: ProjectPaths) -> ImportManager:
        if paths.engine is None or paths.project_id is None:
            raise RuntimeError("workspace database is not open")

        def uow_factory() -> UnitOfWork:
            return UnitOfWork(paths.engine)  # type: ignore[arg-type]

        def index_factory() -> PersistentIdentityIndex:
            return PersistentIdentityIndex(paths.engine)  # type: ignore[arg-type]

        identity_service = IdentityService(
            uow_factory=uow_factory,
            index_factory=index_factory,
            clock=lambda: datetime.now(UTC),
        )
        return ImportManager(
            registry=self._registry,
            uow_factory=uow_factory,
            identity_service=identity_service,
            chemistry_service=ChemistryService(),
        )

    def _replace_paths(self, paths: ProjectPaths) -> None:
        previous = self._paths
        self._paths = paths
        if previous is not None:
            previous.close()

    @staticmethod
    def _require_source(source: str | Path) -> Path:
        path = Path(str(source).strip()).expanduser()
        if not str(source).strip() or not path.exists():
            raise ValueError("Evidence source does not exist")
        return path

    def _require_workspace(self) -> ProjectPaths:
        paths = self._paths
        if paths is None or paths.project is None:
            raise ValueError("Open a workspace before importing evidence")
        return paths


__all__ = ["WorkspaceController", "WorkspaceState"]
