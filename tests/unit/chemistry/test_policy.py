import pytest
from pydantic import ValidationError

from fidelichem.chemistry.policy import (
    DEFAULT_POLICY,
    ChemistryPolicy,
    default_policy,
)


def test_default_policy_is_the_versioned_identity_policy() -> None:
    policy = default_policy()

    assert policy == DEFAULT_POLICY
    assert policy.policy_id == "fidelichem.rdkit-identity.v1"
    assert policy.state_hash_prefix == "fidelichem.molecular-state.v1"
    assert policy.parent_hash_prefix == "fidelichem.compound-parent.v1"
    assert policy.stereo_signature_prefix == "fidelichem.stereochemistry.v1"
    assert policy.protonation_signature_prefix == "fidelichem.protonation.v1"
    assert policy.tautomer_signature_prefix == "fidelichem.tautomer.v1"
    assert policy.max_tautomers == 128
    assert policy.max_transforms == 256
    assert policy.policy_hash == DEFAULT_POLICY.policy_hash


def test_default_policy_is_immutable_and_cannot_be_redefined() -> None:
    original = DEFAULT_POLICY
    with pytest.raises(ValidationError):
        original.max_tautomers = 64  # type: ignore[misc]

    values = original.model_dump()
    values["state_hash_prefix"] = "other.state.v1"
    with pytest.raises(ValidationError, match="policy_id"):
        ChemistryPolicy.model_validate(values)

    assert original.max_tautomers == 128
    assert original.policy_hash == DEFAULT_POLICY.policy_hash
