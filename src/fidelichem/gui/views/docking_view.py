"""Docking analytics and consensus ranking view."""

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


class DockingView(QWidget):
    """View displaying docking runs, scoring methods, and consensus rank percentiles."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)

        title = QLabel("<h2>Docking Analytics & Consensus</h2>", self)
        layout.addWidget(title)

        self.table = QTableWidget(self)
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(
            [
                "Compound",
                "Median %",
                "Mean %",
                "Dispersion",
                "Methods",
            ]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        layout.addWidget(self.table)

    def set_consensus_rankings(
        self,
        rankings: Sequence[tuple[str, float, float, float, int]],
    ) -> None:
        """Populate table with docking consensus scores."""
        self.table.setRowCount(len(rankings))
        for row, (cid, med, mean_val, disp, count) in enumerate(rankings):
            self.table.setItem(row, 0, QTableWidgetItem(cid))
            self.table.setItem(row, 1, QTableWidgetItem(f"{med:.3f}"))
            self.table.setItem(row, 2, QTableWidgetItem(f"{mean_val:.3f}"))
            self.table.setItem(row, 3, QTableWidgetItem(f"{disp:.3f}"))
            self.table.setItem(row, 4, QTableWidgetItem(str(count)))


__all__ = ["DockingView"]
