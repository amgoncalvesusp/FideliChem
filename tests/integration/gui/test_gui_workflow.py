"""Integration tests for main window navigation and multi-view workflow."""

from __future__ import annotations

import pytest
from pytestqt.qtbot import QtBot

from fidelichem.gui.main_window import MainWindow


@pytest.mark.gui
def test_main_window_navigation_and_stack(qtbot: QtBot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitUntil(window.isVisible)

    assert window.windowTitle() == "FideliChem"
    assert window.sidebar.count() == 9

    # Test navigating through sidebar tabs
    for row in range(window.sidebar.count()):
        window.sidebar.setCurrentRow(row)
        assert window.stack.currentIndex() == row

    # Verify each view is accessible
    assert window.project_view is not None
    assert window.compounds_view is not None
    assert window.decision_view is not None

    window.close()
    qtbot.waitUntil(lambda: not window.isVisible())
