"""Export and reproducibility package generation view."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
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

        title = QLabel("<h2>Export & Reproducibility</h2>", self)
        layout.addWidget(title)

        form_layout = QHBoxLayout()
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
        self.path_input.setPlaceholderText("Output destination path")
        form_layout.addWidget(self.path_input)

        self.export_btn = QPushButton("Generate Export", self)
        self.export_btn.clicked.connect(self._on_export_clicked)
        form_layout.addWidget(self.export_btn)
        layout.addLayout(form_layout)

        layout.addWidget(QLabel("<b>Export Options:</b>", self))
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
            "Include Provenance Manifest & SHA-256 Hashes", self
        )
        self.chk_provenance.setChecked(True)
        layout.addWidget(self.chk_provenance)

        self.status_label = QLabel("Ready to export.", self)
        self.status_label.setObjectName("exportStatusLabel")
        layout.addWidget(self.status_label)
        layout.addStretch()

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

    def set_export_status(self, message: str) -> None:
        """Update export status message."""
        self.status_label.setText(message)


__all__ = ["ExportsView"]
