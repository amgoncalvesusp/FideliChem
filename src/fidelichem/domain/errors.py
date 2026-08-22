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


class ChemistryError(DomainError):
    """Base class for safe, stable chemistry diagnostics."""

    default_code = "CHEMISTRY_ERROR"
    code = default_code

    def __init__(self, message: str | None = None, *, code: str | None = None):
        self.code = code or self.default_code
        self.diagnostic_code = self.code
        super().__init__(message or self.code)


class InvalidStructureError(ChemistryError):
    """A supplied structure cannot be represented safely."""

    default_code = "CHEMISTRY_INVALID_STRUCTURE"
    code = default_code


class TautomerEnumerationLimitError(ChemistryError):
    """Configured tautomer enumeration did not complete within policy."""

    default_code = "CHEMISTRY_TAUTOMER_ENUMERATION_INCOMPLETE"
    code = default_code


class AmbiguousParentStructureError(ChemistryError):
    """A structure has multiple organic components without a safe parent."""

    default_code = "CHEMISTRY_PARENT_MULTIORGANIC"
    code = default_code


class AliasConflictError(DomainError):
    """A source alias conflicts with an existing identity record."""

    code = "IDENTITY_ALIAS_CONFLICT"


class IdentityResolutionConflictError(DomainError):
    """An append-only identity decision chain has a concurrent conflict."""

    code = "IDENTITY_RESOLUTION_CONFLICT"
