from pathlib import Path

import pytest
from PySide6.QtGui import QIcon
from pytestqt.qtbot import QtBot

from fidelichem.gui.icon import APP_ICON_PATH, load_app_icon
from fidelichem.gui.main_window import MainWindow


@pytest.mark.gui
def test_application_icon_asset_is_packaged_and_loadable(qtbot: QtBot) -> None:
    assert (
        Path(__file__).parents[3]
        / "src"
        / "fidelichem"
        / "gui"
        / "assets"
        / "fidelichem-mark.svg"
    ) == APP_ICON_PATH
    assert APP_ICON_PATH.is_file()
    assert APP_ICON_PATH.with_suffix(".ico").is_file()
    assert APP_ICON_PATH.with_suffix(".png").is_file()

    icon = load_app_icon()
    assert isinstance(icon, QIcon)
    assert not icon.isNull()


@pytest.mark.gui
def test_main_window_uses_application_icon(qtbot: QtBot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    assert not window.windowIcon().isNull()
