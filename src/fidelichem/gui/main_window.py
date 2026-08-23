"""Main application window for FideliChem desktop interface."""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from .controller import WorkspaceController
from .icon import load_app_icon
from .theme import apply_theme
from .views.compounds_view import CompoundsView
from .views.decision_view import DecisionView
from .views.docking_view import DockingView
from .views.dynamics_view import DynamicsView
from .views.exports_view import ExportsView
from .views.import_view import ImportView
from .views.interactions_view import InteractionsView
from .views.project_view import ProjectView
from .views.qc_view import QCView

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Primary GUI window featuring sidebar and stacked views."""

    def __init__(
        self,
        parent: QWidget | None = None,
        controller: WorkspaceController | None = None,
    ) -> None:
        super().__init__(parent)
        self.controller = controller or WorkspaceController()
        self.setWindowTitle("FideliChem")
        self.setWindowIcon(load_app_icon())
        self.setMinimumSize(980, 640)
        self.resize(1180, 760)
        apply_theme(self)

        central_container = QWidget(self)
        root_layout = QHBoxLayout(central_container)
        root_layout.setContentsMargins(16, 16, 16, 10)
        root_layout.setSpacing(14)

        sidebar_panel = QFrame(central_container)
        sidebar_panel.setObjectName("sidebarPanel")
        sidebar_panel.setFixedWidth(208)
        sidebar_layout = QVBoxLayout(sidebar_panel)
        sidebar_layout.setContentsMargins(12, 16, 12, 12)
        sidebar_layout.setSpacing(4)

        brand = QLabel("FIDELICHEM", sidebar_panel)
        brand.setObjectName("brandMark")
        sidebar_layout.addWidget(brand)
        brand_caption = QLabel("Evidence workspace", sidebar_panel)
        brand_caption.setObjectName("brandCaption")
        sidebar_layout.addWidget(brand_caption)
        sidebar_layout.addSpacing(18)

        nav_label = QLabel("WORKSPACE", sidebar_panel)
        nav_label.setObjectName("sectionLabel")
        sidebar_layout.addWidget(nav_label)

        self.sidebar = QListWidget(sidebar_panel)
        self.sidebar.setObjectName("sidebarNav")
        nav_items = [
            "Project",
            "Import",
            "Compounds",
            "Docking",
            "Interactions",
            "Dynamics",
            "Decision",
            "QC",
            "Exports",
        ]
        self.sidebar.addItems(nav_items)
        self.sidebar.currentRowChanged.connect(self._on_nav_changed)
        sidebar_layout.addWidget(self.sidebar, 1)

        self.workspace_badge = QLabel("No workspace selected", sidebar_panel)
        self.workspace_badge.setObjectName("statusBadge")
        self.workspace_badge.setWordWrap(True)
        sidebar_layout.addWidget(self.workspace_badge)
        root_layout.addWidget(sidebar_panel)

        self.stack = QStackedWidget(central_container)
        self.project_view = ProjectView(self.stack)
        self.import_view = ImportView(self.stack)
        self.import_view.set_workspace_ready(False)
        self.compounds_view = CompoundsView(self.stack)
        self.docking_view = DockingView(self.stack)
        self.interactions_view = InteractionsView(self.stack)
        self.dynamics_view = DynamicsView(self.stack)
        self.decision_view = DecisionView(self.stack)
        self.qc_view = QCView(self.stack)
        self.exports_view = ExportsView(self.stack)
        self.exports_view.set_workspace_ready(False)

        self.stack.addWidget(self.project_view)
        self.stack.addWidget(self.import_view)
        self.stack.addWidget(self.compounds_view)
        self.stack.addWidget(self.docking_view)
        self.stack.addWidget(self.interactions_view)
        self.stack.addWidget(self.dynamics_view)
        self.stack.addWidget(self.decision_view)
        self.stack.addWidget(self.qc_view)
        self.stack.addWidget(self.exports_view)

        root_layout.addWidget(self.stack)
        self.setCentralWidget(central_container)

        self.empty_state = QLabel("No project is open.", self)
        self.empty_state.setObjectName("emptyStateLabel")
        self.empty_state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_state.hide()

        self.status_bar = QStatusBar(self)
        self.status_bar.showMessage("Ready · Select a workspace to begin")
        self.setStatusBar(self.status_bar)

        self.project_view.project_created.connect(self._on_project_created)
        self.project_view.project_opened.connect(self._on_project_opened)
        self.import_view.probe_requested.connect(self._on_probe_requested)
        self.import_view.import_requested.connect(self._on_import_requested)
        self.exports_view.export_requested.connect(self._on_export_requested)

        self.sidebar.setCurrentRow(0)

    def _on_nav_changed(self, row: int) -> None:
        if 0 <= row < self.stack.count():
            self.stack.setCurrentIndex(row)
            item = self.sidebar.item(row)
            nav_text = item.text() if item else ""
            self.status_bar.showMessage(f"{nav_text} · FideliChem evidence workspace")

    def _on_project_created(self, name: str, path: str) -> None:
        """Reflect the active project without putting persistence rules in views."""

        try:
            state = self.controller.create_workspace(name, path)
        except Exception as exc:  # noqa: BLE001
            self.project_view.status_label.setText(
                "Workspace could not be created. Check the path and permissions."
            )
            self._show_controller_error("Workspace could not be created", exc)
            return
        self.project_view.set_active_project(state.name, str(state.root))
        self.workspace_badge.setText(f"{state.name}\n{state.root}")
        self.exports_view.set_workspace_ready(True)
        self.import_view.set_workspace_ready(True)
        self.exports_view.set_default_destination(str(state.root / "exports"))
        self.status_bar.showMessage(f"Workspace ready · {state.name}")

    def _on_project_opened(self, path: str) -> None:
        """Reflect an opened project path in the shell status area."""

        try:
            state = self.controller.open_workspace(path)
        except Exception as exc:  # noqa: BLE001
            self.project_view.status_label.setText(
                "Workspace could not be opened. Check the path and permissions."
            )
            self._show_controller_error("Workspace could not be opened", exc)
            return
        self.project_view.set_active_project(state.name, str(state.root))
        self.workspace_badge.setText(f"{state.name}\n{state.root}")
        self.exports_view.set_workspace_ready(True)
        self.import_view.set_workspace_ready(True)
        self.exports_view.set_default_destination(str(state.root / "exports"))
        self.status_bar.showMessage(f"Workspace opened · {state.name}")

    def _on_probe_requested(self, adapter_id: str, source: str) -> None:
        try:
            reports = self.controller.probe(adapter_id, source)
            if not reports:
                preview = "No adapter detected. Check the source path and format."
            else:
                preview = "\n".join(self._format_report(report) for report in reports)
            self.import_view.set_probe_preview(preview)
            self.status_bar.showMessage(
                "Probe complete · review the preview before importing"
            )
        except Exception as exc:  # noqa: BLE001
            self.import_view.set_probe_preview(
                f"Probe failed: {self._error_detail(exc)}"
            )
            self._show_controller_error("Probe could not be completed", exc)

    def _on_import_requested(self, adapter_id: str, source: str) -> None:
        try:
            result = self.controller.import_evidence(adapter_id, source)
            self.import_view.set_probe_preview(
                "Import completed\n"
                f"Batch: {result.batch.id}\n"
                f"Adapter: {result.batch.adapter_id}\n"
                f"Compounds: {len(result.bundle.compounds)}\n"
                f"Warnings: {len(result.validation.warnings)}"
            )
            self.status_bar.showMessage("Import completed · evidence is auditable")
        except Exception as exc:  # noqa: BLE001
            self.import_view.set_probe_preview(
                f"Import failed: {self._error_detail(exc)}"
            )
            self._show_controller_error("Import could not be completed", exc)

    def _on_export_requested(
        self,
        format_name: str,
        destination: str,
        options: dict[str, object],
    ) -> None:
        format_map = {
            "CSV": "csv",
            "Excel (XLSX)": "xlsx",
            "Parquet": "parquet",
            "JSON Bundle": "json",
            "Full Audit Report": "methods_report",
        }
        try:
            from fidelichem.exports.models import ExportFormat, ExportOptions

            export_format = ExportFormat(format_map.get(format_name, "csv"))
            export_options = ExportOptions(
                formats=(export_format,),
                include_scores=bool(options.get("scores", True)),
                include_interactions=bool(options.get("interactions", True)),
                include_dynamics=bool(options.get("md", True)),
                include_provenance=bool(options.get("provenance", True)),
            )
            self.controller.export_project(
                destination,
                formats=(export_format,),
                options=export_options,
            )
        except Exception as exc:  # noqa: BLE001
            self.exports_view.set_export_status(
                "Export not generated: import completed evidence or "
                "verify the workspace."
            )
            self._show_controller_error("Export could not be completed", exc)
            return
        self.exports_view.set_export_status("Export completed.")
        self.status_bar.showMessage("Export completed · manifest written")

    @staticmethod
    def _format_report(report: object) -> str:
        confidence = getattr(report, "confidence", 0.0)
        adapter = getattr(report, "suggested_adapter", "unknown")
        detected = getattr(report, "detected_format", "unknown")
        warnings = getattr(report, "warnings", ())
        line = f"{adapter}: {detected} · confidence {confidence:.0%}"
        if warnings:
            line += f"\nWarnings: {'; '.join(str(item) for item in warnings)}"
        return line

    def _show_controller_error(self, context: str, error: Exception) -> None:
        """Log the diagnostic and expose a concise actionable detail in the UI."""

        logger.exception("%s: %s", context, error)
        detail = self._error_detail(error)
        self.status_bar.showMessage(
            f"{context}: {detail}"
        )

    @staticmethod
    def _error_detail(error: Exception) -> str:
        """Return a bounded, single-line error suitable for the status area."""
        detail = " ".join(str(error).split())
        return detail[:240] if detail else "check the selected path and workspace"

    def closeEvent(self, event: object) -> None:  # noqa: N802
        self.controller.close()
        super().closeEvent(event)  # type: ignore[arg-type]


__all__ = ["MainWindow"]
