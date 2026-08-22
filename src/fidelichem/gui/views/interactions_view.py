"""Intermolecular interactions and contact prevalence view."""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtWidgets import (
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class InteractionsView(QWidget):
    """View displaying interaction matrix, contact prevalence, and pose families."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)

        title = QLabel("<h2>Interactions & Contact Prevalence</h2>", self)
        layout.addWidget(title)

        self.table = QTableWidget(self)
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(
            [
                "Residue",
                "Type",
                "Observed / Total",
                "Frequency",
                "Mean Distance (Å)",
            ]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        layout.addWidget(self.table)

    def set_prevalences(
        self,
        records: Sequence[tuple[str, str, int, int, float, float | None]],
    ) -> None:
        """Populate table with contact prevalence entries."""
        self.table.setRowCount(len(records))
        for row, (res, itype, obs, tot, freq, dist) in enumerate(records):
            self.table.setItem(row, 0, QTableWidgetItem(res))
            self.table.setItem(row, 1, QTableWidgetItem(itype))
            self.table.setItem(row, 2, QTableWidgetItem(f"{obs} / {tot}"))
            self.table.setItem(row, 3, QTableWidgetItem(f"{freq * 100:.1f}%"))
            dist_str = f"{dist:.2f}" if dist is not None else "-"
            self.table.setItem(row, 4, QTableWidgetItem(dist_str))


__all__ = ["InteractionsView"]
