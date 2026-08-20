import io
import logging

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

import fidelichem.gui.application as application_module
from fidelichem.gui.application import create_application, main


@pytest.mark.gui
def test_create_application_reuses_qtbot_application(
    qapp: QApplication,
) -> None:
    assert create_application([]) is qapp


@pytest.mark.gui
def test_application_main_runs_until_clean_quit(qapp: QApplication) -> None:
    QTimer.singleShot(0, qapp.quit)

    assert main([]) == 0


@pytest.mark.gui
def test_application_main_logs_startup_failure_and_returns_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = io.StringIO()
    logger = logging.getLogger("test.fidelichem.gui.application")
    handler = logging.StreamHandler(output)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    def fail_to_create_application(
        argv: list[str] | None = None,
    ) -> QApplication:
        del argv
        raise RuntimeError("controlled startup failure")

    monkeypatch.setattr(application_module, "configure_logging", lambda: logger)
    monkeypatch.setattr(
        application_module,
        "create_application",
        fail_to_create_application,
    )

    try:
        assert main([]) == 1
    finally:
        logger.removeHandler(handler)
        handler.close()

    log_output = output.getvalue()
    assert "FideliChem application startup failed" in log_output
    assert "controlled startup failure" in log_output
    assert "Traceback" in log_output
