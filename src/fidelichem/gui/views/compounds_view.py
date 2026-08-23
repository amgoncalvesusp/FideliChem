"""Compound Explorer view with 3-pane architecture and evidence tabs."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHeaderView,
    QLabel,
    QLineEdit,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class CompoundsView(QWidget):
    """3-pane compound explorer displaying candidates, identity, and evidence."""

    compound_selected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(12)

        title = QLabel("Compound explorer", self)
        title.setObjectName("pageTitle")
        main_layout.addWidget(title)
        subtitle = QLabel(
            "Inspect identity, pose evidence, interactions and provenance "
            "side by side.",
            self,
        )
        subtitle.setObjectName("pageSubtitle")
        main_layout.addWidget(subtitle)

        splitter = QSplitter(self)

        # Pane 1: Search & Table
        pane_left = QWidget(self)
        left_layout = QVBoxLayout(pane_left)
        left_layout.setContentsMargins(0, 0, 6, 0)
        self.search_input = QLineEdit(pane_left)
        self.search_input.setAccessibleName("Compound search")
        self.search_input.setPlaceholderText("Search compounds or SMILES...")
        left_layout.addWidget(self.search_input)

        self.table = QTableWidget(pane_left)
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["ID", "Name", "Formula"])
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        left_layout.addWidget(self.table)
        splitter.addWidget(pane_left)

        # Pane 2: 2D info & Identity details
        pane_center = QWidget(self)
        center_layout = QVBoxLayout(pane_center)
        center_layout.setContentsMargins(6, 0, 6, 0)
        center_layout.addWidget(QLabel("<b>Molecule Identity:</b>", pane_center))
        self.identity_text = QTextEdit(pane_center)
        self.identity_text.setReadOnly(True)
        center_layout.addWidget(self.identity_text)
        splitter.addWidget(pane_center)

        # Pane 3: Evidence Tabs
        pane_right = QWidget(self)
        right_layout = QVBoxLayout(pane_right)
        right_layout.setContentsMargins(6, 0, 0, 0)
        self.tabs = QTabWidget(pane_right)

        self.tab_chemistry = QTextEdit(self.tabs)
        self.tab_chemistry.setReadOnly(True)
        self.tabs.addTab(self.tab_chemistry, "Chemistry")

        self.tab_docking = QTextEdit(self.tabs)
        self.tab_docking.setReadOnly(True)
        self.tabs.addTab(self.tab_docking, "Docking")

        self.tab_poses = QTextEdit(self.tabs)
        self.tab_poses.setReadOnly(True)
        self.tabs.addTab(self.tab_poses, "Poses")

        self.tab_interactions = QTextEdit(self.tabs)
        self.tab_interactions.setReadOnly(True)
        self.tabs.addTab(self.tab_interactions, "Interactions")

        self.tab_md = QTextEdit(self.tabs)
        self.tab_md.setReadOnly(True)
        self.tabs.addTab(self.tab_md, "MD")

        self.tab_provenance = QTextEdit(self.tabs)
        self.tab_provenance.setReadOnly(True)
        self.tabs.addTab(self.tab_provenance, "Provenance")

        right_layout.addWidget(self.tabs)
        splitter.addWidget(pane_right)

        splitter.setSizes([300, 300, 360])
        main_layout.addWidget(splitter)

    def _on_selection_changed(self) -> None:
        selected_items = self.table.selectedItems()
        if selected_items:
            row = selected_items[0].row()
            cid_item = self.table.item(row, 0)
            if cid_item:
                self.compound_selected.emit(cid_item.text())

    def set_compounds(self, compounds: Sequence[tuple[str, str, str]]) -> None:
        """Populate compound table with (id, name, formula) tuples."""
        self.table.setRowCount(len(compounds))
        for row, (cid, name, formula) in enumerate(compounds):
            self.table.setItem(row, 0, QTableWidgetItem(cid))
            self.table.setItem(row, 1, QTableWidgetItem(name))
            self.table.setItem(row, 2, QTableWidgetItem(formula))

    def set_compound_details(
        self,
        identity_info: str,
        evidence: dict[str, Any] | None = None,
    ) -> None:
        """Update center and right panes with evidence for selected candidate."""
        self.identity_text.setText(identity_info)
        ev = evidence or {}
        self.tab_chemistry.setText(str(ev.get("chemistry", "")))
        self.tab_docking.setText(str(ev.get("docking", "")))
        self.tab_poses.setText(str(ev.get("poses", "")))
        self.tab_interactions.setText(str(ev.get("interactions", "")))
        self.tab_md.setText(str(ev.get("md", "")))
        self.tab_provenance.setText(str(ev.get("provenance", "")))


__all__ = ["CompoundsView"]
