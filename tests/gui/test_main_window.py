import pytest
from PySide6.QtWidgets import QLabel
from pytestqt.qtbot import QtBot

from fidelichem.gui.main_window import MainWindow


@pytest.mark.gui
def test_main_window_shows_domain_free_empty_state(qtbot: QtBot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    window.show()
    qtbot.waitUntil(window.isVisible)
    empty_state = window.findChild(QLabel, "emptyStateLabel")

    assert window.windowTitle() == "FideliChem"
    assert empty_state is not None
    assert empty_state.property("text") == "No project is open."

    window.close()
    qtbot.waitUntil(lambda: not window.isVisible())
