"""Frozen, versioned parameters for the RDKit identity boundary."""

from __future__ import annotations

from pydantic import Field, model_validator

from fidelichem.domain.chemistry import NonBlankText
from fidelichem.domain.models import DomainModel
from fidelichem.provenance.hashing import sha256_bytes

_DEFAULT_POLICY_ID = "fidelichem.rdkit-identity.v1"
_DEFAULT_VALUES: dict[str, object] = {
    "policy_id": _DEFAULT_POLICY_ID,
    "state_hash_prefix": "fidelichem.molecular-state.v1",
    "parent_hash_prefix": "fidelichem.compound-parent.v1",
    "stereo_signature_prefix": "fidelichem.stereochemistry.v1",
    "protonation_signature_prefix": "fidelichem.protonation.v1",
    "tautomer_signature_prefix": "fidelichem.tautomer.v1",
    "max_tautomers": 128,
    "max_transforms": 256,
}


class ChemistryPolicy(DomainModel):
    """Immutable algorithm and hash contract for canonicalization."""

    policy_id: NonBlankText
    state_hash_prefix: NonBlankText
    parent_hash_prefix: NonBlankText
    stereo_signature_prefix: NonBlankText
    protonation_signature_prefix: NonBlankText
    tautomer_signature_prefix: NonBlankText
    max_tautomers: int = Field(ge=1, strict=True)
    max_transforms: int = Field(ge=1, strict=True)

    @model_validator(mode="after")
    def _reject_redefinition(self) -> ChemistryPolicy:
        if self.policy_id == _DEFAULT_POLICY_ID:
            for field, expected in _DEFAULT_VALUES.items():
                if getattr(self, field) != expected:
                    raise ValueError(
                        "policy_id is already assigned to a different algorithm"
                    )
        return self

    @property
    def hash_payload(self) -> bytes:
        """Return the exact UTF-8 payload used to identify this policy."""

        values = (
            self.policy_id,
            self.state_hash_prefix,
            self.parent_hash_prefix,
            self.stereo_signature_prefix,
            self.protonation_signature_prefix,
            self.tautomer_signature_prefix,
            str(self.max_tautomers),
            str(self.max_transforms),
        )
        return "\0".join(values).encode("utf-8")

    @property
    def policy_hash(self) -> str:
        return sha256_bytes(self.hash_payload)

DEFAULT_POLICY = ChemistryPolicy.model_validate(_DEFAULT_VALUES)


def default_policy() -> ChemistryPolicy:
    """Return the only configured initial chemistry policy."""

    return DEFAULT_POLICY


def hash_payload(prefix: str, payload: str) -> str:
    """Hash a versioned descriptor payload without changing its text."""

    return f"{prefix}:{sha256_bytes(payload.encode('utf-8'))}"


def state_hash(policy: ChemistryPolicy, state_smiles: str) -> str:
    return sha256_bytes(
        f"{policy.state_hash_prefix}\0{state_smiles}".encode()
    )


def parent_hash(policy: ChemistryPolicy, parent_smiles: str) -> str:
    return sha256_bytes(
        f"{policy.parent_hash_prefix}\0{parent_smiles}".encode()
    )


__all__ = [
    "DEFAULT_POLICY",
    "ChemistryPolicy",
    "default_policy",
    "hash_payload",
    "parent_hash",
    "state_hash",
]
