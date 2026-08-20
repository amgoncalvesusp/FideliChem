import os
import subprocess
import sys

import pytest


@pytest.mark.smoke
def test_headless_gui_process_starts_event_loop_and_exits() -> None:
    script = """
from PySide6.QtCore import QTimer
from fidelichem.gui.application import create_application, main

application = create_application([])
QTimer.singleShot(0, application.quit)
raise SystemExit(main([]))
"""
    environment = os.environ | {"QT_QPA_PLATFORM": "offscreen"}

    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        check=False,
        env=environment,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0
    assert "Traceback" not in result.stderr
