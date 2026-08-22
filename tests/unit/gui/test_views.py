"""Unit tests for individual GUI views."""

from __future__ import annotations

import pytest
from pytestqt.qtbot import QtBot

from fidelichem.gui.views.compounds_view import CompoundsView
from fidelichem.gui.views.decision_view import DecisionView
from fidelichem.gui.views.docking_view import DockingView
from fidelichem.gui.views.dynamics_view import DynamicsView
from fidelichem.gui.views.exports_view import ExportsView
from fidelichem.gui.views.import_view import ImportView
from fidelichem.gui.views.interactions_view import InteractionsView
from fidelichem.gui.views.project_view import ProjectView
from fidelichem.gui.views.qc_view import QCView


@pytest.mark.gui
def test_project_view_lifecycle(qtbot: QtBot) -> None:
    view = ProjectView()
    qtbot.addWidget(view)

    view.set_active_project("TestProj", "/path/to/proj")
    assert "TestProj" in view.status_label.text()
    assert view.name_input.text() == "TestProj"


@pytest.mark.gui
def test_import_view_probe_and_preview(qtbot: QtBot) -> None:
    view = ImportView()
    qtbot.addWidget(view)

    view.path_input.setText("/path/to/gold_run")
    view.set_probe_preview("Detected GOLD docking folder: 10 ligands")
    assert "GOLD" in view.preview_text.toPlainText()


@pytest.mark.gui
def test_compounds_view_population(qtbot: QtBot) -> None:
    view = CompoundsView()
    qtbot.addWidget(view)

    view.set_compounds(
        [
            ("C1", "Erlotinib", "C22H23N3O4"),
            ("C2", "Gefitinib", "C22H24ClFN4O3"),
        ]
    )
    assert view.table.rowCount() == 2
    assert view.table.item(0, 1).text() == "Erlotinib"

    view.set_compound_details(
        identity_info="InChIKey=... Canonical SMILES=...",
        evidence={
            "docking": "GoldScore: 78.5",
            "interactions": "MET793: H-bond",
        },
    )
    assert "InChIKey" in view.identity_text.toPlainText()
    assert "GoldScore" in view.tab_docking.toPlainText()


@pytest.mark.gui
def test_docking_view_rankings(qtbot: QtBot) -> None:
    view = DockingView()
    qtbot.addWidget(view)

    view.set_consensus_rankings(
        [
            ("C1", 0.95, 0.92, 0.04, 3),
            ("C2", 0.85, 0.82, 0.06, 3),
        ]
    )
    assert view.table.rowCount() == 2
    assert view.table.item(0, 1).text() == "0.950"


@pytest.mark.gui
def test_interactions_view_prevalences(qtbot: QtBot) -> None:
    view = InteractionsView()
    qtbot.addWidget(view)

    view.set_prevalences(
        [
            ("MET793", "hbond", 8, 10, 0.80, 2.85),
        ]
    )
    assert view.table.rowCount() == 1
    assert view.table.item(0, 0).text() == "MET793"
    assert view.table.item(0, 3).text() == "80.0%"


@pytest.mark.gui
def test_dynamics_view_metrics(qtbot: QtBot) -> None:
    view = DynamicsView()
    qtbot.addWidget(view)

    view.set_metrics(
        [
            ("md_run_1", "Ligand RMSD", 0.18, 0.02, "nm"),
        ]
    )
    assert view.table.rowCount() == 1
    assert view.table.item(0, 0).text() == "md_run_1"


@pytest.mark.gui
def test_decision_view_triage_and_explanations(qtbot: QtBot) -> None:
    view = DecisionView()
    qtbot.addWidget(view)

    view.set_decisions(
        [
            (
                1,
                "C1",
                "ADVANCE",
                0.92,
                ["top 5% ChemPLP", "MET793 H-bond conserved"],
                [],
                [],
                [],
            ),
            (
                2,
                "C2",
                "HOLD",
                0.55,
                [],
                ["missing MD evidence"],
                ["SA score 4.8"],
                ["Run 50ns MD simulation"],
            ),
        ]
    )
    assert view.table.rowCount() == 2
    assert view.table.item(0, 2).text() == "ADVANCE"
    assert view.table.item(1, 2).text() == "HOLD"


@pytest.mark.gui
def test_qc_view_issues(qtbot: QtBot) -> None:
    view = QCView()
    qtbot.addWidget(view)

    view.set_qc_issues(
        [
            ("WARNING", "gold_adapter", "Missing atom coords in pose 3", "C1"),
        ]
    )
    assert view.table.rowCount() == 1
    assert view.table.item(0, 0).text() == "WARNING"


@pytest.mark.gui
def test_exports_view_options(qtbot: QtBot) -> None:
    view = ExportsView()
    qtbot.addWidget(view)

    assert view.format_combo.count() >= 3
    view.set_export_status("Export completed.")
    assert view.status_label.text() == "Export completed."
