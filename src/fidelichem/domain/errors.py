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
    public_message = "chemistry operation failed"

    def __init__(self) -> None:
        self.diagnostic_code = self.code
        super().__init__(self.public_message)

    @property
    def message(self) -> str:
        return self.public_message


class IdentityError(DomainError):
    """Base class for safe, stable identity diagnostics."""

    default_code = "IDENTITY_ERROR"
    code = default_code
    public_message = "identity operation failed"

    def __init__(self) -> None:
        self.diagnostic_code = self.code
        super().__init__(self.public_message)

    @property
    def message(self) -> str:
        return self.public_message


class InvalidStructureError(ChemistryError):
    """A supplied structure cannot be represented safely."""

    default_code = "CHEMISTRY_INVALID_STRUCTURE"
    code = default_code
    public_message = "input structure is invalid"


class TautomerEnumerationLimitError(ChemistryError):
    """Configured tautomer enumeration did not complete within policy."""

    default_code = "CHEMISTRY_TAUTOMER_ENUMERATION_INCOMPLETE"
    code = default_code
    public_message = "tautomer enumeration did not complete"


class AmbiguousParentStructureError(ChemistryError):
    """A structure has multiple organic components without a safe parent."""

    default_code = "CHEMISTRY_PARENT_MULTIORGANIC"
    code = default_code
    public_message = "structure has an ambiguous organic parent"


class NoOrganicParentStructureError(ChemistryError):
    """A structure has no carbon-containing organic component."""

    default_code = "CHEMISTRY_PARENT_NO_ORGANIC"
    code = default_code
    public_message = "structure has no organic parent"


class ParentPolicyMismatchError(ChemistryError):
    """RDKit's parent representative violates the configured policy."""

    default_code = "CHEMISTRY_PARENT_POLICY_MISMATCH"
    code = default_code
    public_message = "structure parent policy could not be applied"


class AliasConflictError(IdentityError):
    """A source alias conflicts with an existing identity record."""

    code = "IDENTITY_ALIAS_CONFLICT"
    public_message = "identity alias conflicts with an existing record"


class IdentityResolutionConflictError(IdentityError):
    """An append-only identity decision chain has a concurrent conflict."""

    code = "IDENTITY_RESOLUTION_CONFLICT"
    public_message = "identity resolution conflicts with the existing chain"


class AdapterError(DomainError):
    """Base class for adapter-related errors."""


class AdapterNotFoundError(AdapterError):
    """An adapter with the specified identifier is not registered."""


class AdapterExecutionError(AdapterError):
    """An adapter crashed or failed unexpectedly during execution."""


class ImportError(DomainError):
    """Base class for import-related errors."""


class DuplicateImportError(ImportError):
    """A batch with identical inputs has already been imported into the project."""


class ImportValidationError(ImportError):
    """An import bundle failed domain or adapter validation."""
