"""Quality control diagnostics and issue inspection view."""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class QCView(QWidget):
    """View displaying QC issues, severity levels, and diagnostic records."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)

        title = QLabel("<h2>Quality Control Diagnostics</h2>", self)
        layout.addWidget(title)

        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Severity Filter:", self))
        self.severity_combo = QComboBox(self)
        self.severity_combo.addItems(["ALL", "ERROR", "WARNING", "INFO"])
        filter_layout.addWidget(self.severity_combo)
        filter_layout.addStretch()
        layout.addLayout(filter_layout)

        self.table = QTableWidget(self)
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(
            [
                "Severity",
                "Category / Adapter",
                "Message",
                "Compound / Entity",
            ]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        layout.addWidget(self.table)

    def set_qc_issues(
        self,
        issues: Sequence[tuple[str, str, str, str]],
    ) -> None:
        """Populate table with QC diagnostic records."""
        self.table.setRowCount(len(issues))
        for row, (sev, cat, msg, ent) in enumerate(issues):
            self.table.setItem(row, 0, QTableWidgetItem(sev))
            self.table.setItem(row, 1, QTableWidgetItem(cat))
            self.table.setItem(row, 2, QTableWidgetItem(msg))
            self.table.setItem(row, 3, QTableWidgetItem(ent))


__all__ = ["QCView"]
