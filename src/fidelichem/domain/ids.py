"""Factories and validators for opaque application identifiers."""

from uuid import RFC_4122, UUID, uuid4

from .errors import InvalidIdentifierError


def new_id() -> str:
    """Return a fresh opaque UUID4 identifier in canonical text form."""

    return str(uuid4())


def validate_id(value: object) -> str:
    """Validate and normalize an opaque UUID4 identifier."""

    if not isinstance(value, str):
        raise InvalidIdentifierError("identifier must be a UUID4 string")
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError, TypeError) as exc:
        raise InvalidIdentifierError("identifier must be a UUID4 string") from exc
    if value != str(parsed) or parsed.version != 4 or parsed.variant != RFC_4122:
        raise InvalidIdentifierError("identifier must be a UUID4 string")
    return str(parsed)


def new_uuid4() -> str:
    """Backward-compatible explicit name for :func:`new_id`."""

    return new_id()
