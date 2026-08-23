"""Export and reproducibility package generation view."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class ExportsView(QWidget):
    """View configuring and generating CSV, Excel, Parquet, and bundles."""

    export_requested = Signal(str, str, dict)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(12)

        title = QLabel("Export & reproducibility", self)
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        subtitle = QLabel(
            "Package selected evidence with provenance and stable output paths.", self
        )
        subtitle.setObjectName("pageSubtitle")
        layout.addWidget(subtitle)

        form_layout = QHBoxLayout()
        form_layout.setSpacing(8)
        form_layout.addWidget(QLabel("Export Format:", self))
        self.format_combo = QComboBox(self)
        self.format_combo.addItems(
            [
                "CSV",
                "Excel (XLSX)",
                "Parquet",
                "JSON Bundle",
                "Full Audit Report",
            ]
        )
        form_layout.addWidget(self.format_combo)

        self.path_input = QLineEdit(self)
        self.path_input.setAccessibleName("Export destination")
        self.path_input.setPlaceholderText("Output destination path")
        self.path_input.textChanged.connect(self._sync_action_state)
        form_layout.addWidget(self.path_input)

        self.browse_btn = QPushButton("Choose Folder", self)
        self.browse_btn.setAccessibleName("Choose export folder")
        self.browse_btn.setProperty("role", "secondary")
        self.browse_btn.clicked.connect(self._on_browse_clicked)
        form_layout.addWidget(self.browse_btn)

        self.export_btn = QPushButton("Generate Export", self)
        self.export_btn.setProperty("role", "primary")
        self.export_btn.clicked.connect(self._on_export_clicked)
        form_layout.addWidget(self.export_btn)
        layout.addLayout(form_layout)

        options_label = QLabel("EXPORT CONTENT", self)
        options_label.setObjectName("sectionLabel")
        layout.addWidget(options_label)
        self.chk_scores = QCheckBox("Include Docking Scores & Consensus Rankings", self)
        self.chk_scores.setChecked(True)
        layout.addWidget(self.chk_scores)

        self.chk_interactions = QCheckBox(
            "Include Intermolecular Contact Matrices", self
        )
        self.chk_interactions.setChecked(True)
        layout.addWidget(self.chk_interactions)

        self.chk_md = QCheckBox(
            "Include Molecular Dynamics Curves & Summary Stats", self
        )
        self.chk_md.setChecked(True)
        layout.addWidget(self.chk_md)

        self.chk_provenance = QCheckBox(
            "Include Import Batch Provenance Columns", self
        )
        self.chk_provenance.setChecked(True)
        layout.addWidget(self.chk_provenance)

        self.status_label = QLabel("Ready to export.", self)
        self.status_label.setObjectName("exportStatusLabel")
        layout.addWidget(self.status_label)
        layout.addStretch()
        self._workspace_ready = False
        self._sync_action_state(self.path_input.text())

    def _sync_action_state(self, path: str) -> None:
        self.export_btn.setEnabled(self._workspace_ready and bool(path.strip()))

    def _on_export_clicked(self) -> None:
        fmt = self.format_combo.currentText()
        dest = self.path_input.text().strip()
        options = {
            "scores": self.chk_scores.isChecked(),
            "interactions": self.chk_interactions.isChecked(),
            "md": self.chk_md.isChecked(),
            "provenance": self.chk_provenance.isChecked(),
        }
        self.export_requested.emit(fmt, dest, options)
        self.status_label.setText(f"Export requested for format {fmt}")

    def _on_browse_clicked(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self,
            "Choose export folder",
            self.path_input.text().strip(),
        )
        if path:
            self.path_input.setText(path)

    def set_export_status(self, message: str) -> None:
        """Update export status message."""
        self.status_label.setText(message)

    def set_workspace_ready(self, ready: bool) -> None:
        """Enable export only when one workspace is active."""

        self._workspace_ready = ready
        self._sync_action_state(self.path_input.text())

    def set_default_destination(self, path: str) -> None:
        """Use the workspace export directory as the default output path."""

        self.path_input.setText(path)


__all__ = ["ExportsView"]
