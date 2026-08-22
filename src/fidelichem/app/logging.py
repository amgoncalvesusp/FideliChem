import logging

_LOGGER_NAME = "fidelichem"
_HANDLER_NAME = "fidelichem.console"
_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def _resolve_level(level: int | str) -> int:
    if isinstance(level, int):
        return level

    resolved = logging.getLevelNamesMapping().get(level.upper())
    if resolved is None:
        raise ValueError(f"Unknown logging level: {level}")
    return resolved


def configure_logging(level: int | str = logging.INFO) -> logging.Logger:
    resolved_level = _resolve_level(level)
    logger = logging.getLogger(_LOGGER_NAME)
    owned_handlers = tuple(
        handler for handler in logger.handlers if handler.get_name() == _HANDLER_NAME
    )

    if owned_handlers:
        handler = owned_handlers[0]
        for duplicate in owned_handlers[1:]:
            logger.removeHandler(duplicate)
            duplicate.close()
    else:
        handler = logging.StreamHandler()
        handler.set_name(_HANDLER_NAME)
        logger.addHandler(handler)

    handler.setFormatter(logging.Formatter(_FORMAT))
    handler.setLevel(resolved_level)
    logger.setLevel(resolved_level)
    logger.propagate = False
    return logger
