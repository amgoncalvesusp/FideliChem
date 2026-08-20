import logging
import sys
from collections.abc import Sequence

from PySide6.QtWidgets import QApplication

from fidelichem.app.logging import configure_logging
from fidelichem.gui.main_window import MainWindow


def create_application(argv: Sequence[str] | None = None) -> QApplication:
    existing = QApplication.instance()
    if existing is None:
        arguments = list(argv) if argv is not None else list(sys.argv)
        return QApplication(arguments)
    if not isinstance(existing, QApplication):
        raise RuntimeError("An incompatible Qt core application already exists")
    return existing


def main(argv: Sequence[str] | None = None) -> int:
    logger: logging.Logger | None = None
    try:
        logger = configure_logging()
        application = create_application(argv)
        window = MainWindow()
        window.show()
        logger.info("FideliChem application started")
        exit_code = application.exec()
    except Exception:
        failure_logger = logger if logger is not None else logging.getLogger()
        failure_logger.exception("FideliChem application startup failed")
        return 1

    logger.info("FideliChem application stopped with exit code %s", exit_code)
    return exit_code
