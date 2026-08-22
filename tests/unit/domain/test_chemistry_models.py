from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

import fidelichem.domain as public_domain
from fidelichem.domain.chemistry import (
    Alias,
    CanonicalizationResult,
    ChemistryWarning,
    ChemistryWarningCode,
    Compound,
    IdentityActor,
    IdentityClaim,
    IdentityDecision,
    IdentityResolution,
    IdentitySelection,
    MolecularState,
    SelectionMode,
)
from fidelichem.domain.errors import (
    AliasConflictError,
    AmbiguousParentStructureError,
    ChemistryError,
    IdentityError,
    IdentityResolutionConflictError,
    InvalidStructureError,
    NoOrganicParentStructureError,
    ParentPolicyMismatchError,
    TautomerEnumerationLimitError,
)
from fidelichem.domain.models import ActorKind

NOW = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)
COMPOUND_ID = "11111111-1111-4111-8111-111111111111"
STATE_ID = "22222222-2222-4222-8222-222222222222"
ALIAS_ID = "33333333-3333-4333-8333-333333333333"
BATCH_ID = "44444444-4444-4444-8444-444444444444"
HASH = "a" * 64
INCHI = "UHOVQNZJYSORNB-UHFFFAOYSA-N"


def valid_compound(**updates: object) -> Compound:
    values: dict[str, object] = {
        "id": COMPOUND_ID,
        "canonical_smiles": "CCO",
        "isomeric_smiles": "CCO",
        "inchikey": INCHI,
        "formula": "C2H6O",
        "molecular_weight": 46.069,
        "structure_hash": HASH,
        "chemistry_policy_id": "fidelichem.rdkit-identity.v1",
        "rdkit_version": "2026.3.4",
        "inchi_version": "1S",
        "created_at": NOW,
    }
    values.update(updates)
    return Compound.model_validate(values)


def valid_state(**updates: object) -> MolecularState:
    values: dict[str, object] = {
        "id": STATE_ID,
        "compound_id": COMPOUND_ID,
        "state_smiles": "CCO",
        "state_inchikey": INCHI,
        "formal_charge": 0,
        "stereochemistry_signature": "fidelichem.stereochemistry.v1:" + HASH,
        "protonation_signature": "fidelichem.protonation.v1:" + HASH,
        "tautomer_signature": "fidelichem.tautomer.v1:" + HASH,
        "state_hash": HASH,
        "chemistry_policy_id": "fidelichem.rdkit-identity.v1",
        "rdkit_version": "2026.3.4",
        "inchi_version": "1S",
        "preparation_ph": 7.4,
    }
    values.update(updates)
    return MolecularState.model_validate(values)


def valid_alias(**updates: object) -> Alias:
    values: dict[str, object] = {
        "id": ALIAS_ID,
        "source_system": "gold",
        "source_value": "Ligand-17",
        "import_batch_id": BATCH_ID,
        "created_at": NOW,
    }
    values.update(updates)
    return Alias.model_validate(values)


def test_chemistry_values_are_frozen_and_reject_extra_fields() -> None:
    compound = valid_compound()
    with pytest.raises(ValidationError):
        compound.formula = "other"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        valid_compound(unexpected=True)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("molecular_weight", 0),
        ("molecular_weight", float("inf")),
        ("molecular_weight", float("nan")),
        ("preparation_ph", -0.1),
        ("preparation_ph", 14.1),
        ("preparation_ph", float("nan")),
    ],
)
def test_compound_and_state_numeric_bounds_are_strict(
    field: str, value: object
) -> None:
    with pytest.raises(ValidationError):
        if field == "molecular_weight":
            valid_compound(**{field: value})
        else:
            valid_state(**{field: value})


@pytest.mark.parametrize("value", [True, False])
def test_mass_and_ph_reject_boolean_numbers(value: bool) -> None:
    with pytest.raises(ValidationError):
        valid_compound(molecular_weight=value)
    with pytest.raises(ValidationError):
        valid_state(preparation_ph=value)


def test_optional_inchi_keys_accept_none_but_reject_empty_values() -> None:
    assert valid_compound(inchikey=None).inchikey is None
    assert valid_state(state_inchikey=None).state_inchikey is None
    with pytest.raises(ValidationError):
        valid_compound(inchikey="")
    with pytest.raises(ValidationError):
        valid_state(state_inchikey="")


def test_nonblank_policy_and_runtime_provenance_is_required() -> None:
    for field in ("chemistry_policy_id", "rdkit_version"):
        with pytest.raises(ValidationError):
            valid_compound(**{field: "  "})


@pytest.mark.parametrize(
    "value",
    ["Gold", "_gold", "-gold", "", "a" * 129, "gold\x00source"],
)
def test_source_system_uses_bounded_lowercase_slug(value: str) -> None:
    with pytest.raises(ValidationError):
        valid_alias(source_system=value)


@pytest.mark.parametrize("value", ["", "   ", "a\x00b", "a" * 1025])
def test_alias_source_value_rejects_blank_nul_and_oversized_values(value: str) -> None:
    with pytest.raises(ValidationError):
        valid_alias(source_value=value)


@pytest.mark.parametrize(
    ("source_system", "source_value"),
    [("gold", None), (None, "Ligand-17")],
)
def test_identity_claim_source_pair_is_both_or_neither(
    source_system: str | None, source_value: str | None
) -> None:
    with pytest.raises(ValidationError, match="together"):
        IdentityClaim(
            source_system=source_system,
            source_value=source_value,
            smiles=None,
            inchikey=None,
            import_batch_id=None,
        )


def test_identity_claim_without_persistence_fields_is_resolver_usable() -> None:
    claim = IdentityClaim(
        source_system=None,
        source_value=None,
        smiles="[CH3:7][OH]",
        inchikey=None,
        import_batch_id=None,
    )
    assert claim.source_system is None
    assert claim.smiles == "[CH3:7][OH]"


def test_identity_resolution_decision_truth_table() -> None:
    common = {
        "alias_id": ALIAS_ID,
        "decided_at": NOW,
        "actor_kind": ActorKind.SYSTEM,
        "actor_id": None,
        "rationale": None,
    }
    confirmed = IdentityResolution(
        **common,
        decision=IdentityDecision.CONFIRMED,
        compound_id=COMPOUND_ID,
        molecular_state_id=STATE_ID,
        supersedes_id=None,
    )
    reassigned = IdentityResolution(
        **common,
        decision=IdentityDecision.REASSIGNED,
        compound_id=COMPOUND_ID,
        molecular_state_id=None,
        supersedes_id=ALIAS_ID,
    )
    retracted = IdentityResolution(
        **common,
        decision=IdentityDecision.RETRACTED,
        compound_id=None,
        molecular_state_id=None,
        supersedes_id=ALIAS_ID,
    )
    restored_values = {
        **common,
        "actor_kind": ActorKind.USER,
        "actor_id": "reviewer",
        "rationale": "restore after review",
    }
    restored = IdentityResolution(
        **restored_values,
        decision=IdentityDecision.RESTORED,
        compound_id=COMPOUND_ID,
        molecular_state_id=STATE_ID,
        supersedes_id=ALIAS_ID,
    )
    assert [
        confirmed.decision,
        reassigned.decision,
        retracted.decision,
        restored.decision,
    ] == list(IdentityDecision)


@pytest.mark.parametrize(
    "updates",
    [
        {"decision": IdentityDecision.CONFIRMED, "supersedes_id": ALIAS_ID},
        {"decision": IdentityDecision.REASSIGNED, "supersedes_id": None},
        {"decision": IdentityDecision.RETRACTED, "compound_id": COMPOUND_ID},
        {"decision": IdentityDecision.RESTORED, "actor_kind": ActorKind.SYSTEM},
        {"decision": IdentityDecision.RESTORED, "rationale": "  "},
    ],
)
def test_identity_resolution_rejects_invalid_decision_shapes(
    updates: dict[str, object],
) -> None:
    values: dict[str, object] = {
        "alias_id": ALIAS_ID,
        "decision": IdentityDecision.CONFIRMED,
        "compound_id": COMPOUND_ID,
        "molecular_state_id": STATE_ID,
        "supersedes_id": None,
        "decided_at": NOW,
        "actor_kind": ActorKind.SYSTEM,
        "actor_id": None,
        "rationale": None,
    }
    values.update(updates)
    with pytest.raises(ValidationError):
        IdentityResolution.model_validate(values)


def test_selection_modes_enforce_target_shapes() -> None:
    assert (
        IdentitySelection(
            mode=SelectionMode.EXISTING_TARGET,
            compound_id=COMPOUND_ID,
            molecular_state_id=STATE_ID,
        ).compound_id
        == COMPOUND_ID
    )
    assert (
        IdentitySelection(
            mode=SelectionMode.NEW_COMPOUND,
            compound_id=None,
            molecular_state_id=None,
        ).mode
        is SelectionMode.NEW_COMPOUND
    )
    with pytest.raises(ValidationError):
        IdentitySelection(
            mode=SelectionMode.EXISTING_TARGET,
            compound_id=None,
            molecular_state_id=STATE_ID,
        )
    with pytest.raises(ValidationError):
        IdentitySelection(
            mode=SelectionMode.NEW_COMPOUND,
            compound_id=COMPOUND_ID,
            molecular_state_id=None,
        )


def test_identity_actor_rules_are_frozen_and_bounded() -> None:
    assert (
        IdentityActor(
            kind=ActorKind.USER,
            actor_id="reviewer",
            rationale="manual review",
        ).actor_id
        == "reviewer"
    )
    assert (
        IdentityActor(
            kind=ActorKind.SYSTEM,
            actor_id=None,
            rationale=None,
        ).kind
        is ActorKind.SYSTEM
    )
    with pytest.raises(ValidationError):
        IdentityActor(kind=ActorKind.SYSTEM, actor_id="service", rationale=None)
    with pytest.raises(ValidationError):
        IdentityActor(kind=ActorKind.USER, actor_id="  ", rationale=None)
    with pytest.raises(ValidationError):
        IdentityActor(kind=ActorKind.USER, actor_id="x" * 129, rationale=None)
    with pytest.raises(ValidationError):
        IdentityActor(kind=ActorKind.USER, actor_id="ok", rationale="x" * 1025)


def test_warning_codes_and_source_smiles_are_preserved() -> None:
    warning = ChemistryWarning(
        code=ChemistryWarningCode.INCHI_UNAVAILABLE,
        message="InChI generation unavailable",
    )
    result = CanonicalizationResult(
        source_smiles="[CH3:7][OH]",
        compound=valid_compound(inchikey=None),
        molecular_state=valid_state(state_inchikey=None),
        chemistry_policy_id="fidelichem.rdkit-identity.v1",
        warnings=(warning,),
    )
    assert result.source_smiles == "[CH3:7][OH]"
    assert result.warnings[0].code.value == "inchi_unavailable"


@pytest.mark.parametrize(
    "updates",
    [
        {"compound": valid_compound(chemistry_policy_id="other.policy")},
        {"molecular_state": valid_state(chemistry_policy_id="other.policy")},
        {"compound": valid_compound(rdkit_version="2026.4.0")},
        {"molecular_state": valid_state(rdkit_version="2026.4.0")},
        {"compound": valid_compound(inchi_version="2S")},
        {"molecular_state": valid_state(inchi_version="2S")},
        {
            "molecular_state": valid_state(
                compound_id="55555555-5555-4555-8555-555555555555"
            )
        },
    ],
)
def test_canonicalization_result_rejects_inconsistent_bundle(
    updates: dict[str, object],
) -> None:
    values: dict[str, object] = {
        "source_smiles": "[CH3:7][OH]",
        "compound": valid_compound(inchikey=None),
        "molecular_state": valid_state(state_inchikey=None),
        "chemistry_policy_id": "fidelichem.rdkit-identity.v1",
        "warnings": (),
    }
    values.update(updates)
    with pytest.raises(ValidationError, match="consistent"):
        CanonicalizationResult.model_validate(values)


@pytest.mark.parametrize(
    ("actor_kind", "actor_id"),
    [(ActorKind.SYSTEM, "service"), (ActorKind.USER, None)],
)
def test_identity_resolution_rejects_invalid_actor_branches(
    actor_kind: ActorKind, actor_id: str | None
) -> None:
    with pytest.raises(ValidationError, match="actor"):
        IdentityResolution(
            alias_id=ALIAS_ID,
            decision=IdentityDecision.CONFIRMED,
            compound_id=COMPOUND_ID,
            molecular_state_id=None,
            supersedes_id=None,
            decided_at=NOW,
            actor_kind=actor_kind,
            actor_id=actor_id,
            rationale=None,
        )


def test_typed_chemistry_and_identity_errors_have_stable_codes() -> None:
    assert NoOrganicParentStructureError.code == "CHEMISTRY_PARENT_NO_ORGANIC"
    assert ParentPolicyMismatchError.code == "CHEMISTRY_PARENT_POLICY_MISMATCH"
    errors = (
        InvalidStructureError(),
        TautomerEnumerationLimitError(),
        AmbiguousParentStructureError(),
        NoOrganicParentStructureError(),
        ParentPolicyMismatchError(),
        AliasConflictError(),
        IdentityResolutionConflictError(),
    )
    for error in errors:
        assert error.code
        assert str(error)
        assert "raw" not in str(error)
        assert "SELECT" not in str(error)


@pytest.mark.parametrize(
    "error_type",
    [
        InvalidStructureError,
        TautomerEnumerationLimitError,
        AmbiguousParentStructureError,
        NoOrganicParentStructureError,
        ParentPolicyMismatchError,
        AliasConflictError,
        IdentityResolutionConflictError,
    ],
)
def test_public_domain_errors_reject_message_and_code_overrides(
    error_type: type[ValueError],
) -> None:
    with pytest.raises(TypeError):
        error_type("raw SMILES", code="SELECT * FROM secret")  # type: ignore[call-arg]


def test_identity_conflicts_are_not_chemistry_errors_and_aliases_are_private() -> None:
    assert issubclass(AliasConflictError, IdentityError)
    assert issubclass(IdentityResolutionConflictError, IdentityError)
    assert not issubclass(AliasConflictError, ChemistryError)
    assert not issubclass(IdentityResolutionConflictError, ChemistryError)

    with pytest.raises(IdentityError):
        raise AliasConflictError()
    try:
        raise IdentityResolutionConflictError()
    except ChemistryError:
        pytest.fail("identity conflicts must not be caught as chemistry errors")
    except IdentityError:
        pass

    assert not hasattr(public_domain, "NoOrganicParentError")
    assert not hasattr(public_domain, "NoOrganicStructureError")
    assert not hasattr(public_domain, "FragmentParentPolicyError")
