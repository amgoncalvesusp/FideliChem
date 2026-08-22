"""Evidence import view with probing preview and execution."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class ImportView(QWidget):
    """View handling adapter selection, probing preview, and import."""

    probe_requested = Signal(str, str)
    import_requested = Signal(str, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)

        title = QLabel("<h2>Evidence Importer</h2>", self)
        layout.addWidget(title)

        adapter_layout = QHBoxLayout()
        adapter_layout.addWidget(QLabel("Adapter:", self))
        self.adapter_combo = QComboBox(self)
        self.adapter_combo.addItems(
            [
                "auto",
                "gold",
                "smiles2select",
                "smiles2docking",
                "docklens",
                "gromacs",
                "moldynstudio",
                "universal_table",
            ]
        )
        adapter_layout.addWidget(self.adapter_combo)

        self.path_input = QLineEdit(self)
        self.path_input.setPlaceholderText("Path to data folder or file")
        adapter_layout.addWidget(self.path_input)

        self.probe_btn = QPushButton("Probe Data", self)
        self.probe_btn.clicked.connect(self._on_probe_clicked)
        adapter_layout.addWidget(self.probe_btn)

        self.import_btn = QPushButton("Execute Import", self)
        self.import_btn.clicked.connect(self._on_import_clicked)
        adapter_layout.addWidget(self.import_btn)
        layout.addLayout(adapter_layout)

        layout.addWidget(QLabel("Probe Preview:", self))
        self.preview_text = QTextEdit(self)
        self.preview_text.setReadOnly(True)
        self.preview_text.setObjectName("importPreviewText")
        layout.addWidget(self.preview_text)

    def _on_probe_clicked(self) -> None:
        adapter = self.adapter_combo.currentText()
        path = self.path_input.text().strip()
        if path:
            self.probe_requested.emit(adapter, path)

    def _on_import_clicked(self) -> None:
        adapter = self.adapter_combo.currentText()
        path = self.path_input.text().strip()
        if path:
            self.import_requested.emit(adapter, path)

    def set_probe_preview(self, preview_summary: str) -> None:
        """Display probing outcome before persisting."""
        self.preview_text.setText(preview_summary)


__all__ = ["ImportView"]
