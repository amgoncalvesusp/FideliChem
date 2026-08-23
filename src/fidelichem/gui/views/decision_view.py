"""Multi-fidelity decision triage and transparent explanation view."""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtWidgets import (
    QHeaderView,
    QLabel,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class DecisionView(QWidget):
    """View displaying triage priorities, rankings, and explanations."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(12)

        title = QLabel("Decision engine & triage", self)
        title.setObjectName("pageTitle")
        main_layout.addWidget(title)
        subtitle = QLabel(
            "Make next-evidence choices transparent and reviewable.", self
        )
        subtitle.setObjectName("pageSubtitle")
        main_layout.addWidget(subtitle)

        splitter = QSplitter(self)

        # Left: Decision table
        table_container = QWidget(self)
        table_layout = QVBoxLayout(table_container)
        self.table = QTableWidget(table_container)
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(
            [
                "Rank",
                "Compound",
                "Priority",
                "Composite Score",
            ]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        table_layout.addWidget(self.table)
        splitter.addWidget(table_container)

        # Right: Explanations panel
        details_container = QWidget(self)
        details_layout = QVBoxLayout(details_container)
        details_layout.setContentsMargins(6, 0, 0, 0)
        details_layout.addWidget(
            QLabel(
                "<b>Justifications & Recommended Next Evidence:</b>",
                details_container,
            )
        )
        self.explanation_text = QTextEdit(details_container)
        self.explanation_text.setReadOnly(True)
        details_layout.addWidget(self.explanation_text)
        splitter.addWidget(details_container)

        splitter.setSizes([500, 400])
        main_layout.addWidget(splitter)
        self._explanations: dict[str, str] = {}

    def _on_selection_changed(self) -> None:
        selected_items = self.table.selectedItems()
        if selected_items:
            row = selected_items[0].row()
            cid_item = self.table.item(row, 1)
            if cid_item and cid_item.text() in self._explanations:
                self.explanation_text.setText(self._explanations[cid_item.text()])

    def set_decisions(
        self,
        decisions: Sequence[
            tuple[
                int,
                str,
                str,
                float | None,
                Sequence[str],
                Sequence[str],
                Sequence[str],
                Sequence[str],
            ]
        ],
    ) -> None:
        """Populate decision table and cache structured explanations."""
        self.table.setRowCount(len(decisions))
        self._explanations.clear()

        for row, (
            rank,
            cid,
            priority,
            score,
            pos,
            neg,
            warns,
            recs,
        ) in enumerate(decisions):
            self.table.setItem(row, 0, QTableWidgetItem(str(rank)))
            self.table.setItem(row, 1, QTableWidgetItem(cid))
            self.table.setItem(row, 2, QTableWidgetItem(priority))
            score_str = f"{score:.3f}" if score is not None else "-"
            self.table.setItem(row, 3, QTableWidgetItem(score_str))

            # Build formatted explanation text
            exp_lines = [f"### Candidate {cid} — {priority}"]
            if score is not None:
                exp_lines.append(f"Composite Score: {score:.3f} (Rank #{rank})")
            exp_lines.append("\n**Positive Factors:**")
            if pos:
                for p in pos:
                    exp_lines.append(f"+ {p}")
            else:
                exp_lines.append("(None)")

            exp_lines.append("\n**Negative Factors / Missing Evidence:**")
            if neg:
                for n in neg:
                    exp_lines.append(f"- {n}")
            else:
                exp_lines.append("(None)")

            if warns:
                exp_lines.append("\n**Warnings:**")
                for w in warns:
                    exp_lines.append(f"! {w}")

            if recs:
                exp_lines.append("\n**Recommended Next Evidence:**")
                for r in recs:
                    exp_lines.append(f"> {r}")

            self._explanations[cid] = "\n".join(exp_lines)


__all__ = ["DecisionView"]
