"""Application icon loading kept in one small, testable boundary."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QIcon

APP_ICON_PATH = Path(__file__).with_name("assets") / "fidelichem-mark.svg"


def load_app_icon() -> QIcon:
    """Return the packaged FideliChem mark for windows and the app shell."""

    return QIcon(str(APP_ICON_PATH))
