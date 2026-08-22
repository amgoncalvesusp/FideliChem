"""Main application window for FideliChem desktop interface."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QStackedWidget,
    QStatusBar,
    QWidget,
)

from .views.compounds_view import CompoundsView
from .views.decision_view import DecisionView
from .views.docking_view import DockingView
from .views.dynamics_view import DynamicsView
from .views.exports_view import ExportsView
from .views.import_view import ImportView
from .views.interactions_view import InteractionsView
from .views.project_view import ProjectView
from .views.qc_view import QCView


class MainWindow(QMainWindow):
    """Primary GUI window featuring sidebar and stacked views."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("FideliChem")
        self.resize(1100, 720)

        central_container = QWidget(self)
        root_layout = QHBoxLayout(central_container)
        root_layout.setContentsMargins(4, 4, 4, 4)

        self.sidebar = QListWidget(central_container)
        self.sidebar.setObjectName("sidebarNav")
        self.sidebar.setFixedWidth(180)
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
        root_layout.addWidget(self.sidebar)

        self.stack = QStackedWidget(central_container)
        self.project_view = ProjectView(self.stack)
        self.import_view = ImportView(self.stack)
        self.compounds_view = CompoundsView(self.stack)
        self.docking_view = DockingView(self.stack)
        self.interactions_view = InteractionsView(self.stack)
        self.dynamics_view = DynamicsView(self.stack)
        self.decision_view = DecisionView(self.stack)
        self.qc_view = QCView(self.stack)
        self.exports_view = ExportsView(self.stack)

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
        self.status_bar.showMessage("Ready")
        self.setStatusBar(self.status_bar)

        self.sidebar.setCurrentRow(0)

    def _on_nav_changed(self, row: int) -> None:
        if 0 <= row < self.stack.count():
            self.stack.setCurrentIndex(row)
            item = self.sidebar.item(row)
            nav_text = item.text() if item else ""
            self.status_bar.showMessage(f"Active View: {nav_text}")


__all__ = ["MainWindow"]
