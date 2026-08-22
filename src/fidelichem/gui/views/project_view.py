"""Project management view for creating, opening, and inspecting projects."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class ProjectView(QWidget):
    """View managing project lifecycle, workspace path, and metadata."""

    project_created = Signal(str, str)
    project_opened = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)

        title = QLabel("<h2>Project Management</h2>", self)
        layout.addWidget(title)

        form_layout = QHBoxLayout()
        self.name_input = QLineEdit(self)
        self.name_input.setPlaceholderText("Project name (e.g. EGFR Virtual Screening)")
        form_layout.addWidget(self.name_input)

        self.path_input = QLineEdit(self)
        self.path_input.setPlaceholderText("Storage folder path")
        form_layout.addWidget(self.path_input)

        self.create_btn = QPushButton("Create Project", self)
        self.create_btn.clicked.connect(self._on_create_clicked)
        form_layout.addWidget(self.create_btn)
        layout.addLayout(form_layout)

        self.status_label = QLabel("No project loaded.", self)
        self.status_label.setObjectName("projectStatusLabel")
        layout.addWidget(self.status_label)
        layout.addStretch()

    def _on_create_clicked(self) -> None:
        name = self.name_input.text().strip()
        path = self.path_input.text().strip()
        if name:
            self.project_created.emit(name, path)
            self.status_label.setText(f"Active Project: {name}")

    def set_active_project(self, name: str, path: str) -> None:
        """Update view state with active project information."""
        self.name_input.setText(name)
        self.path_input.setText(path)
        self.status_label.setText(f"Active Project: {name} ({path})")


__all__ = ["ProjectView"]
