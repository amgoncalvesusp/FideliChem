import threading
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

import fidelichem.chemistry.service as chemistry_service
from fidelichem.chemistry import ChemistryService
from fidelichem.chemistry.policy import ChemistryPolicy
from fidelichem.domain.chemistry import ChemistryWarningCode
from fidelichem.domain.errors import (
    AmbiguousParentStructureError,
    ChemistryError,
    InvalidStructureError,
    NoOrganicParentStructureError,
    ParentPolicyMismatchError,
    TautomerEnumerationLimitError,
)

NOW = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)
VALID_INCHI = "LFQSCWFLJHTTHZ-UHFFFAOYSA-N"


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
    mapped = service.canonicalize("[CH3:7][CH2:2][OH:99]", created_at=NOW)

    assert mapped.molecular_state.state_hash == unmapped.molecular_state.state_hash
    assert mapped.compound.structure_hash == unmapped.compound.structure_hash
    assert mapped.source_smiles == "[CH3:7][CH2:2][OH:99]"
    assert ":" not in mapped.molecular_state.state_smiles


def test_mol2_smiles_falls_back_to_tripos_graph(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Read MOPAC-style MOL2 when RDKit rejects the metadata."""
    block = (
        "@<TRIPOS>MOLECULE\n"
        "ETHANOL\n"
        " 3 2 0 0 0\n"
        "SMALL\nNO_CHARGES\n\n"
        "@<TRIPOS>ATOM\n"
        " 1 C1 0.0 0.0 0.0 C.3 1 LIG 0.0\n"
        " 2 C2 1.5 0.0 0.0 C.3 1 LIG 0.0\n"
        " 3 O3 2.5 0.0 0.0 O.3 1 LIG 0.0\n"
        "@<TRIPOS>BOND\n"
        " 1 1 2 1\n"
        " 2 2 3 1\n"
    )
    monkeypatch.setattr(
        chemistry_service.Chem,
        "MolFromMol2Block",
        lambda *args, **kwargs: None,
    )
    assert ChemistryService.derive_smiles_from_mol2_block(block) == "CCO"


def test_service_policy_binding_is_read_only(service: ChemistryService) -> None:
    with pytest.raises((AttributeError, TypeError)):
        service.policy = ChemistryPolicy.model_validate(
            {
                "policy_id": "fidelichem.rdkit-identity.v2",
                "state_hash_prefix": "fidelichem.molecular-state.v2",
                "parent_hash_prefix": "fidelichem.compound-parent.v2",
                "stereo_signature_prefix": "fidelichem.stereochemistry.v2",
                "protonation_signature_prefix": "fidelichem.protonation.v2",
                "tautomer_signature_prefix": "fidelichem.tautomer.v2",
                "max_tautomers": 128,
                "max_transforms": 256,
            }
        )


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


def test_tautomer_uses_completed_result_pick_canonical_once_per_enumerator(
    service: ChemistryService, monkeypatch: pytest.MonkeyPatch
) -> None:
    import fidelichem.chemistry.service as service_module

    instances: list[object] = []

    class CompletedEnumerator:
        def __init__(self) -> None:
            self.enumerate_calls = 0
            self.pick_calls = 0
            instances.append(self)

        def SetMaxTautomers(self, value: int) -> None:
            assert value == 128

        def SetMaxTransforms(self, value: int) -> None:
            assert value == 256

        def Enumerate(self, mol: object) -> SimpleNamespace:
            self.enumerate_calls += 1
            return SimpleNamespace(status="Completed", mol=mol)

        def PickCanonical(self, result: SimpleNamespace) -> object:
            self.pick_calls += 1
            return result.mol

        def Canonicalize(self, _mol: object) -> object:
            raise AssertionError("legacy Canonicalize path must not be used")

    monkeypatch.setattr(
        service_module.rdMolStandardize, "TautomerEnumerator", CompletedEnumerator
    )
    service.canonicalize("CCO", created_at=NOW)
    assert len(instances) == 2
    assert all(item.enumerate_calls == 1 for item in instances)
    assert all(item.pick_calls == 1 for item in instances)


def test_inchi_unavailable_is_nullable_warning(
    service: ChemistryService, monkeypatch: pytest.MonkeyPatch
) -> None:
    import fidelichem.chemistry.service as service_module

    monkeypatch.setattr(service_module.inchi, "MolToInchiKey", lambda _mol: "")
    result = service.canonicalize("CCO", created_at=NOW)
    assert result.compound.inchikey is None
    assert result.molecular_state.state_inchikey is None
    assert result.warnings[0].code is ChemistryWarningCode.INCHI_UNAVAILABLE


@pytest.mark.parametrize(
    ("keys", "expected_state", "expected_parent"),
    [
        (("not-a-key", VALID_INCHI), None, VALID_INCHI),
        ((VALID_INCHI, "not-a-key"), VALID_INCHI, None),
        (("lfqscwfljhtthz-uhvfaoysa-n", VALID_INCHI), None, VALID_INCHI),
    ],
)
def test_malformed_inchi_key_is_nullable_independently(
    service: ChemistryService,
    monkeypatch: pytest.MonkeyPatch,
    keys: tuple[str, str],
    expected_state: str | None,
    expected_parent: str | None,
) -> None:
    import fidelichem.chemistry.service as service_module

    pending = list(keys)
    monkeypatch.setattr(
        service_module.inchi, "MolToInchiKey", lambda _mol: pending.pop(0)
    )
    result = service.canonicalize("CCO", created_at=NOW)
    assert result.molecular_state.state_inchikey == expected_state
    assert result.compound.inchikey == expected_parent
    assert result.warnings[0].code is ChemistryWarningCode.INCHI_UNAVAILABLE


@pytest.mark.parametrize(
    "target",
    ["MolToSmiles", "GetFormalCharge"],
)
def test_rdkit_state_derivation_failures_are_safe(
    service: ChemistryService,
    monkeypatch: pytest.MonkeyPatch,
    target: str,
) -> None:
    import fidelichem.chemistry.service as service_module

    monkeypatch.setattr(
        service_module.Chem,
        target,
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("raw diagnostic")),
    )
    with pytest.raises(ChemistryError) as raised:
        service.canonicalize("CCO", created_at=NOW)
    assert "raw diagnostic" not in str(raised.value)


@pytest.mark.parametrize("module_name", ["rdMolDescriptors", "Descriptors"])
def test_rdkit_formula_and_mass_failures_are_safe(
    service: ChemistryService,
    monkeypatch: pytest.MonkeyPatch,
    module_name: str,
) -> None:
    import fidelichem.chemistry.service as service_module

    module = getattr(service_module, module_name)
    target = "CalcMolFormula" if module_name == "rdMolDescriptors" else "MolWt"
    monkeypatch.setattr(
        module,
        target,
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("raw diagnostic")),
    )
    with pytest.raises(ChemistryError) as raised:
        service.canonicalize("CCO", created_at=NOW)
    assert "raw diagnostic" not in str(raised.value)


def test_nested_rdkit_log_blocks_are_scoped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import fidelichem.chemistry.service as service_module

    enters = 0
    exits = 0

    class Blocker:
        def __enter__(self) -> None:
            nonlocal enters
            enters += 1

        def __exit__(self, *_args: object) -> None:
            nonlocal exits
            exits += 1

    monkeypatch.setattr(service_module.rdBase, "BlockLogs", Blocker)
    with service_module._quiet_rdkit():
        with service_module._quiet_rdkit():
            assert enters == 2
            assert exits == 0
        assert exits == 1
    assert exits == 2


def test_rdkit_log_suppression_regions_do_not_overlap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import fidelichem.chemistry.service as service_module

    first_entered = threading.Event()
    second_attempted = threading.Event()
    second_entered = threading.Event()
    release_first = threading.Event()
    overlap = False
    sentinels: list[str] = []
    active = 0
    state_lock = threading.Lock()

    class Blocker:
        def __enter__(self) -> None:
            nonlocal active, overlap
            with state_lock:
                active += 1
                overlap = overlap or active > 1
                if active > 1:
                    sentinels.append("log re-enabled during another region")

        def __exit__(self, *_args: object) -> None:
            nonlocal active
            with state_lock:
                active -= 1

    def first_worker() -> None:
        with service_module._quiet_rdkit():
            first_entered.set()
            assert release_first.wait(timeout=2)

    def second_worker() -> None:
        assert first_entered.wait(timeout=2)
        second_attempted.set()
        with service_module._quiet_rdkit():
            second_entered.set()

    monkeypatch.setattr(service_module.rdBase, "BlockLogs", Blocker)
    first = threading.Thread(target=first_worker)
    second = threading.Thread(target=second_worker)
    first.start()
    second.start()
    assert second_attempted.wait(timeout=2)
    try:
        assert not service_module._rdkit_log_lock.acquire(blocking=False)
        assert not second_entered.is_set()
    finally:
        release_first.set()
    first.join(timeout=2)
    second.join(timeout=2)
    assert second_entered.is_set()
    assert not first.is_alive()
    assert not second.is_alive()
    assert not overlap
    assert sentinels == []


def test_parent_policy_mismatch_is_safe_error(
    service: ChemistryService, monkeypatch: pytest.MonkeyPatch
) -> None:
    import fidelichem.chemistry.service as service_module

    def wrong_parent(mol: object) -> object:
        return service_module.Chem.MolFromSmiles("CC")

    monkeypatch.setattr(service_module.rdMolStandardize, "FragmentParent", wrong_parent)
    with pytest.raises(ParentPolicyMismatchError):
        service.canonicalize("CCO.[Cl-]", created_at=NOW)
