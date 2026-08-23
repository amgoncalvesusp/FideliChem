"""Molecular dynamics analytical metrics and trajectory curves view."""

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


class DynamicsView(QWidget):
    """View displaying molecular dynamics runs, metrics, and summaries."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(12)

        title = QLabel("Molecular dynamics analytics", self)
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        subtitle = QLabel(
            "Review trajectory summaries while keeping missing values explicit.", self
        )
        subtitle.setObjectName("pageSubtitle")
        layout.addWidget(subtitle)

        self.table = QTableWidget(self)
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(
            [
                "Run Name",
                "Metric",
                "Mean",
                "Std",
                "Unit",
            ]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        layout.addWidget(self.table)

    def set_metrics(
        self,
        metrics: Sequence[tuple[str, str, float, float, str]],
    ) -> None:
        """Populate table with MD summary metrics."""
        self.table.setRowCount(len(metrics))
        for row, (run_name, metric, mean_val, std_val, unit) in enumerate(metrics):
            self.table.setItem(row, 0, QTableWidgetItem(run_name))
            self.table.setItem(row, 1, QTableWidgetItem(metric))
            self.table.setItem(row, 2, QTableWidgetItem(f"{mean_val:.3f}"))
            self.table.setItem(row, 3, QTableWidgetItem(f"{std_val:.3f}"))
            self.table.setItem(row, 4, QTableWidgetItem(unit))


__all__ = ["DynamicsView"]
