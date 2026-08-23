"""Shell-level GUI tests for navigation and service wiring."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from fidelichem.gui.controller import WorkspaceState
from fidelichem.gui.main_window import MainWindow


class FakeController:
    def __init__(self) -> None:
        self.closed = False
        self.created: tuple[str, str] | None = None
        self.exported: tuple[str, tuple[str, ...]] | None = None

    def create_workspace(self, name: str, root: str) -> WorkspaceState:
        self.created = (name, root)
        return WorkspaceState(name=name, root=Path(root), project_id="project-1")

    def open_workspace(self, root: str) -> WorkspaceState:
        return WorkspaceState(name="Opened", root=Path(root), project_id="project-1")

    def export_project(
        self,
        destination: str,
        *,
        formats: tuple[object, ...],
        options: object | None = None,
    ) -> object:
        del options
        self.exported = (destination, tuple(str(item) for item in formats))
        return object()

    def close(self) -> None:
        self.closed = True


@pytest.mark.gui
def test_main_window_wires_project_actions_and_navigation(qtbot: QtBot) -> None:
    controller = FakeController()
    window = MainWindow(controller=controller)  # type: ignore[arg-type]
    qtbot.addWidget(window)

    window.project_view.name_input.setText("EGFR")
    window.project_view.path_input.setText("C:/workspace/egfr")
    qtbot.mouseClick(window.project_view.create_btn, Qt.MouseButton.LeftButton)

    assert controller.created == ("EGFR", "C:/workspace/egfr")
    assert "EGFR" in window.workspace_badge.text()

    window.sidebar.setCurrentRow(5)
    assert window.stack.currentIndex() == 5
    assert "Dynamics" in window.status_bar.currentMessage()


@pytest.mark.gui
def test_main_window_prefills_export_directory_after_workspace_creation(
    qtbot: QtBot,
) -> None:
    controller = FakeController()
    window = MainWindow(controller=controller)  # type: ignore[arg-type]
    qtbot.addWidget(window)

    assert not window.exports_view.export_btn.isEnabled()

    window.project_view.name_input.setText("EGFR")
    window.project_view.path_input.setText("C:/workspace/egfr")
    qtbot.mouseClick(window.project_view.create_btn, Qt.MouseButton.LeftButton)

    assert Path(window.exports_view.path_input.text()) == Path(
        "C:/workspace/egfr/exports"
    )
    assert window.exports_view.export_btn.isEnabled()

    window.sidebar.setCurrentRow(8)
    qtbot.mouseClick(window.exports_view.export_btn, Qt.MouseButton.LeftButton)

    assert controller.exported is not None
    assert Path(controller.exported[0]) == Path("C:/workspace/egfr/exports")
    assert controller.exported[1] == ("csv",)
