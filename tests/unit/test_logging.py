import logging
from collections.abc import Iterator

import pytest

from fidelichem.app.logging import configure_logging


@pytest.fixture
def isolated_fidelichem_logger() -> Iterator[logging.Logger]:
    logger = logging.getLogger("fidelichem")
    original_handlers = tuple(logger.handlers)
    original_level = logger.level
    original_propagate = logger.propagate

    for handler in tuple(logger.handlers):
        logger.removeHandler(handler)

    yield logger

    for handler in tuple(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    for handler in original_handlers:
        logger.addHandler(handler)
    logger.setLevel(original_level)
    logger.propagate = original_propagate


@pytest.mark.unit
def test_configure_logging_is_idempotent(
    isolated_fidelichem_logger: logging.Logger,
) -> None:
    first = configure_logging("DEBUG")
    second = configure_logging("INFO")
    owned_handlers = [
        handler
        for handler in isolated_fidelichem_logger.handlers
        if handler.get_name() == "fidelichem.console"
    ]

    assert first is isolated_fidelichem_logger
    assert second is isolated_fidelichem_logger
    assert isolated_fidelichem_logger.level == logging.INFO
    assert isolated_fidelichem_logger.propagate is False
    assert len(owned_handlers) == 1
    assert owned_handlers[0].level == logging.INFO


@pytest.mark.unit
def test_configure_logging_rejects_unknown_level(
    isolated_fidelichem_logger: logging.Logger,
) -> None:
    with pytest.raises(ValueError, match="Unknown logging level: VERBOSE"):
        configure_logging("VERBOSE")


@pytest.mark.unit
def test_configure_logging_accepts_integer_level(
    isolated_fidelichem_logger: logging.Logger,
) -> None:
    configured = configure_logging(logging.WARNING)
    owned_handlers = [
        handler
        for handler in isolated_fidelichem_logger.handlers
        if handler.get_name() == "fidelichem.console"
    ]

    assert configured.level == logging.WARNING
    assert len(owned_handlers) == 1
    assert owned_handlers[0].level == logging.WARNING


@pytest.mark.unit
def test_configure_logging_removes_duplicate_owned_handlers(
    isolated_fidelichem_logger: logging.Logger,
) -> None:
    first_duplicate = logging.StreamHandler()
    first_duplicate.set_name("fidelichem.console")
    second_duplicate = logging.StreamHandler()
    second_duplicate.set_name("fidelichem.console")
    isolated_fidelichem_logger.addHandler(first_duplicate)
    isolated_fidelichem_logger.addHandler(second_duplicate)

    configure_logging()
    owned_handlers = [
        handler
        for handler in isolated_fidelichem_logger.handlers
        if handler.get_name() == "fidelichem.console"
    ]

    assert owned_handlers == [first_duplicate]
    assert second_duplicate not in isolated_fidelichem_logger.handlers
    assert second_duplicate._closed is True


@pytest.mark.unit
def test_configure_logging_configures_formatter(
    isolated_fidelichem_logger: logging.Logger,
) -> None:
    configure_logging()
    handler = next(
        handler
        for handler in isolated_fidelichem_logger.handlers
        if handler.get_name() == "fidelichem.console"
    )

    assert handler.formatter is not None
    assert handler.formatter._fmt == (
        "%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
