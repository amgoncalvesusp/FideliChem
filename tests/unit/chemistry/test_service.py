from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from fidelichem.chemistry import ChemistryService
from fidelichem.domain.chemistry import ChemistryWarningCode
from fidelichem.domain.errors import (
    AmbiguousParentStructureError,
    InvalidStructureError,
    NoOrganicParentStructureError,
    ParentPolicyMismatchError,
    TautomerEnumerationLimitError,
)

NOW = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)


@pytest.fixture
def service() -> ChemistryService:
    return ChemistryService()


def test_canonicalization_preserves_source_and_canonicalizes_equivalent_smiles(
    service: ChemistryService,
) -> None:
    cco = service.canonicalize("CCO", created_at=NOW)
    occ = service.canonicalize("OCC", created_at=NOW)

    assert cco.source_smiles == "CCO"
    assert occ.source_smiles == "OCC"
    assert cco.molecular_state.state_hash == occ.molecular_state.state_hash
    assert cco.compound.structure_hash == occ.compound.structure_hash


def test_atom_maps_are_not_identity(service: ChemistryService) -> None:
    unmapped = service.canonicalize("CCO", created_at=NOW)
    mapped = service.canonicalize(
        "[CH3:7][CH2:2][OH:99]", created_at=NOW
    )

    assert mapped.molecular_state.state_hash == unmapped.molecular_state.state_hash
    assert mapped.compound.structure_hash == unmapped.compound.structure_hash
    assert mapped.source_smiles == "[CH3:7][CH2:2][OH:99]"
    assert ":" not in mapped.molecular_state.state_smiles


@pytest.mark.parametrize(
    ("left", "right"),
    [("F/C=C/F", "F/C=C\\F"), ("CN", "C[NH3+]")],
)
def test_exact_state_hash_preserves_stereo_and_charge(
    service: ChemistryService, left: str, right: str
) -> None:
    assert (
        service.canonicalize(left, created_at=NOW).molecular_state.state_hash
        != service.canonicalize(right, created_at=NOW).molecular_state.state_hash
    )


def test_tautomeric_forms_remain_distinct_exact_states(
    service: ChemistryService,
) -> None:
    keto = service.canonicalize("CC(=O)C", created_at=NOW)
    enol = service.canonicalize("CC(O)=C", created_at=NOW)
    assert keto.molecular_state.state_hash != enol.molecular_state.state_hash


def test_one_organic_salt_keeps_exact_state_but_parentizes_organic_component(
    service: ChemistryService,
) -> None:
    result = service.canonicalize("CCO.[Cl-]", created_at=NOW)

    assert "." in result.molecular_state.state_smiles
    assert result.compound.formula == "C2H6O"
    assert result.compound.molecular_weight == pytest.approx(46.069, abs=1e-12)
    assert result.compound.canonical_smiles == "CCO"
    assert result.molecular_state.chemistry_policy_id == result.chemistry_policy_id
    assert result.compound.rdkit_version


@pytest.mark.parametrize("source", ["CCO.CCO", "CCO.CN"])
def test_multiple_organic_components_are_ambiguous(
    service: ChemistryService, source: str
) -> None:
    with pytest.raises(AmbiguousParentStructureError) as raised:
        service.canonicalize(source, created_at=NOW)
    assert raised.value.code == "CHEMISTRY_PARENT_MULTIORGANIC"
    if source:
        assert source not in str(raised.value)


def test_no_organic_component_is_rejected(service: ChemistryService) -> None:
    with pytest.raises(NoOrganicParentStructureError):
        service.canonicalize("[Na+].[Cl-]", created_at=NOW)


@pytest.mark.parametrize(
    "source",
    ["", "   ", "a\x00b", "x" * 10001, "not valid smiles"],
)
def test_untrusted_input_is_rejected_without_echoing_it(
    service: ChemistryService, source: str
) -> None:
    with pytest.raises(InvalidStructureError) as raised:
        service.canonicalize(source, created_at=NOW)
    if source:
        assert source not in str(raised.value)
    assert "SMILES" not in str(raised.value)
    assert "RDKit" not in str(raised.value)


def test_atom_limit_is_bounded_without_exposing_input(
    service: ChemistryService,
) -> None:
    source = ".".join(["C"] * 2001)
    with pytest.raises(InvalidStructureError) as raised:
        service.canonicalize(source, created_at=NOW)
    assert source not in str(raised.value)


def test_tautomer_non_completed_status_is_safe_error(
    service: ChemistryService, monkeypatch: pytest.MonkeyPatch
) -> None:
    import fidelichem.chemistry.service as service_module

    class IncompleteEnumerator:
        def __init__(self) -> None:
            self.max_tautomers = 0
            self.max_transforms = 0

        def SetMaxTautomers(self, value: int) -> None:
            self.max_tautomers = value

        def SetMaxTransforms(self, value: int) -> None:
            self.max_transforms = value

        def Enumerate(self, _mol: object) -> SimpleNamespace:
            return SimpleNamespace(status="Limit")

    monkeypatch.setattr(
        service_module.rdMolStandardize, "TautomerEnumerator", IncompleteEnumerator
    )
    with pytest.raises(TautomerEnumerationLimitError) as raised:
        service.canonicalize("CCO", created_at=NOW)
    assert "Limit" not in str(raised.value)


def test_inchi_unavailable_is_nullable_warning(
    service: ChemistryService, monkeypatch: pytest.MonkeyPatch
) -> None:
    import fidelichem.chemistry.service as service_module

    monkeypatch.setattr(service_module.inchi, "MolToInchiKey", lambda _mol: "")
    result = service.canonicalize("CCO", created_at=NOW)
    assert result.compound.inchikey is None
    assert result.molecular_state.state_inchikey is None
    assert result.warnings[0].code is ChemistryWarningCode.INCHI_UNAVAILABLE


def test_parent_policy_mismatch_is_safe_error(
    service: ChemistryService, monkeypatch: pytest.MonkeyPatch
) -> None:
    import fidelichem.chemistry.service as service_module

    def wrong_parent(mol: object) -> object:
        return service_module.Chem.MolFromSmiles("CC")

    monkeypatch.setattr(service_module.rdMolStandardize, "FragmentParent", wrong_parent)
    with pytest.raises(ParentPolicyMismatchError):
        service.canonicalize("CCO.[Cl-]", created_at=NOW)
