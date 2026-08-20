"""Typed errors raised at the FideliChem domain boundary."""


class DomainError(ValueError):
    """Base class for errors caused by invalid domain data or operations."""


class DomainValidationError(DomainError):
    """Invalid value supplied to a domain primitive."""


class InvalidIdentifierError(DomainValidationError):
    """An identifier is not a canonical UUID4 string."""


class InvalidTimestampError(DomainValidationError):
    """A timestamp is naive or otherwise not representable as UTC."""


class InvalidHashError(DomainValidationError):
    """A digest is not a lowercase hexadecimal SHA-256 value."""


class InvalidJsonError(DomainValidationError):
    """JSON is malformed, non-finite, or contains duplicate object keys."""


class UnsafePathError(DomainValidationError):
    """A relative path could escape its project root or is not POSIX-like."""


class InvalidStatusTransitionError(DomainError):
    """An import batch lifecycle transition is not allowed."""
