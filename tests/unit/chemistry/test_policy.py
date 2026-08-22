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


@pytest.mark.parametrize("field", ["max_tautomers", "max_transforms"])
def test_policy_resource_caps_are_bounded(field: str) -> None:
    values = DEFAULT_POLICY.model_dump()
    values[field] = 129
    with pytest.raises(ValidationError):
        ChemistryPolicy.model_validate(values)


def test_new_policy_id_cannot_reuse_v1_hash_namespaces() -> None:
    values = DEFAULT_POLICY.model_dump()
    values["policy_id"] = "fidelichem.rdkit-identity.v2"
    with pytest.raises(ValidationError, match="prefix"):
        ChemistryPolicy.model_validate(values)
