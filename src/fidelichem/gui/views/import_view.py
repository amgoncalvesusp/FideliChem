"""Evidence import view with probing preview and execution."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
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
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(12)

        title = QLabel("Evidence importer", self)
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        subtitle = QLabel(
            "Probe raw files first, then commit an auditable import.", self
        )
        subtitle.setObjectName("pageSubtitle")
        layout.addWidget(subtitle)

        adapter_layout = QHBoxLayout()
        adapter_layout.setSpacing(8)
        adapter_layout.addWidget(QLabel("Adapter:", self))
        self.adapter_combo = QComboBox(self)
        self.adapter_combo.setAccessibleName("Evidence adapter")
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
        self.path_input.setAccessibleName("Evidence path")
        self.path_input.setPlaceholderText("Path to data folder or file")
        self.path_input.textChanged.connect(self._sync_action_state)
        adapter_layout.addWidget(self.path_input)

        self.browse_folder_btn = QPushButton("Choose Folder", self)
        self.browse_folder_btn.setAccessibleName("Choose evidence folder")
        self.browse_folder_btn.setProperty("role", "secondary")
        self.browse_folder_btn.clicked.connect(self._on_browse_folder_clicked)
        adapter_layout.addWidget(self.browse_folder_btn)

        self.browse_file_btn = QPushButton("Choose File", self)
        self.browse_file_btn.setAccessibleName("Choose evidence file")
        self.browse_file_btn.setProperty("role", "secondary")
        self.browse_file_btn.clicked.connect(self._on_browse_file_clicked)
        adapter_layout.addWidget(self.browse_file_btn)

        self.probe_btn = QPushButton("Probe Data", self)
        self.probe_btn.setProperty("role", "secondary")
        self.probe_btn.clicked.connect(self._on_probe_clicked)
        adapter_layout.addWidget(self.probe_btn)

        self.import_btn = QPushButton("Execute Import", self)
        self.import_btn.setProperty("role", "primary")
        self.import_btn.clicked.connect(self._on_import_clicked)
        adapter_layout.addWidget(self.import_btn)
        layout.addLayout(adapter_layout)

        preview_label = QLabel("PROBE PREVIEW", self)
        preview_label.setObjectName("sectionLabel")
        layout.addWidget(preview_label)
        self.preview_text = QTextEdit(self)
        self.preview_text.setReadOnly(True)
        self.preview_text.setObjectName("importPreviewText")
        layout.addWidget(self.preview_text)
        self._workspace_ready = False
        self._sync_action_state(self.path_input.text())

    def _sync_action_state(self, path: str) -> None:
        enabled = bool(path.strip())
        self.probe_btn.setEnabled(enabled)
        self.import_btn.setEnabled(enabled and self._workspace_ready)

    def set_workspace_ready(self, ready: bool) -> None:
        """Enable committing imports only after a project workspace is open."""
        self._workspace_ready = ready
        self._sync_action_state(self.path_input.text())

    def _on_probe_clicked(self) -> None:
        adapter = self.adapter_combo.currentText()
        path = self.path_input.text().strip()
        if path:
            self.probe_requested.emit(adapter, path)

    def _on_browse_folder_clicked(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self,
            "Choose evidence folder",
            self.path_input.text().strip(),
        )
        if path:
            self.path_input.setText(path)

    def _on_browse_file_clicked(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose evidence file",
            self.path_input.text().strip(),
            "Evidence files (*.csv *.tsv *.txt *.json *.jsonl *.xlsx *.xls *.mol2);;"
            "All files (*)",
        )
        if path:
            self.path_input.setText(path)

    def _on_import_clicked(self) -> None:
        adapter = self.adapter_combo.currentText()
        path = self.path_input.text().strip()
        if path:
            self.import_requested.emit(adapter, path)

    def set_probe_preview(self, preview_summary: str) -> None:
        """Display probing outcome before persisting."""
        self.preview_text.setText(preview_summary)


__all__ = ["ImportView"]
