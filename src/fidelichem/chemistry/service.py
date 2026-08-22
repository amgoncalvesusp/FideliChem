"""Bounded RDKit canonicalization for the chemistry identity boundary."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from importlib import import_module
from threading import RLock
from typing import Any, cast

from fidelichem.domain.chemistry import (
    CanonicalizationResult,
    ChemistryWarning,
    ChemistryWarningCode,
    Compound,
    MolecularState,
)
from fidelichem.domain.errors import (
    AmbiguousParentStructureError,
    InvalidStructureError,
    NoOrganicParentStructureError,
    ParentPolicyMismatchError,
    TautomerEnumerationLimitError,
)

from .policy import (
    DEFAULT_POLICY,
    ChemistryPolicy,
    hash_payload,
    parent_hash,
    state_hash,
)

rdkit = import_module("rdkit")
Chem: Any = import_module("rdkit.Chem")
rdBase: Any = import_module("rdkit.rdBase")
Descriptors: Any = import_module("rdkit.Chem.Descriptors")
inchi: Any = import_module("rdkit.Chem.inchi")
rdMolStandardize: Any = import_module("rdkit.Chem.MolStandardize.rdMolStandardize")
rdMolDescriptors = import_module("rdkit.Chem.rdMolDescriptors")

_EXPECTED_RDKIT_VERSION = (2026, 3, 4)
_MAX_SOURCE_CODEPOINTS = 10_000
_MAX_ATOMS = 2_000
_rdkit_log_lock = RLock()


@contextmanager
def _quiet_rdkit() -> Iterator[None]:
    with _rdkit_log_lock, rdBase.BlockLogs():
        yield


def _runtime_version() -> str:
    value = cast(str, rdkit.__version__)
    try:
        version = tuple(int(part) for part in value.split("."))
    except (AttributeError, ValueError):
        raise InvalidStructureError() from None
    if version != _EXPECTED_RDKIT_VERSION:
        raise InvalidStructureError()
    return value


def _canonical_smiles(mol: Any, *, isomeric: bool) -> str:
    try:
        with _quiet_rdkit():
            return cast(
                str, Chem.MolToSmiles(mol, canonical=True, isomericSmiles=isomeric)
            )
    except Exception:
        raise ParentPolicyMismatchError() from None


def _clear_atom_maps(mol: Any) -> Any:
    try:
        with _quiet_rdkit():
            copy = Chem.Mol(mol)
            for atom in copy.GetAtoms():
                atom.SetAtomMapNum(0)
            return copy
    except Exception:
        raise ParentPolicyMismatchError() from None


def _organic_components(mol: Any) -> list[Any]:
    with _quiet_rdkit():
        try:
            fragments = Chem.GetMolFrags(mol, asMols=True, sanitizeFrags=True)
            return [
                fragment
                for fragment in fragments
                if any(atom.GetAtomicNum() == 6 for atom in fragment.GetAtoms())
            ]
        except Exception:
            raise InvalidStructureError() from None


def _same_molecule(left: Any, right: Any) -> bool:
    return _canonical_smiles(left, isomeric=True) == _canonical_smiles(
        right, isomeric=True
    )


def _inchi_key(mol: Any) -> str | None:
    try:
        key = cast(str, inchi.MolToInchiKey(mol))
    except Exception:
        return None
    if not key:
        return None
    if len(key) != 27 or key[14] != "-" or key[25] != "-":
        return None
    uppercase = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    if not (
        all(character in uppercase for character in key[:14])
        and all(character in uppercase for character in key[15:25])
        and key[26] in uppercase
    ):
        return None
    return key


def _inchi_library_version() -> str | None:
    getter = getattr(inchi, "GetInchiVersion", None)
    if getter is None:
        return None
    try:
        value = getter()
    except Exception:
        return None
    return value if isinstance(value, str) and value else None


def _configured_tautomer(mol: Any, policy: ChemistryPolicy) -> Any:
    with _quiet_rdkit():
        try:
            enumerator = rdMolStandardize.TautomerEnumerator()
            enumerator.SetMaxTautomers(policy.max_tautomers)
            enumerator.SetMaxTransforms(policy.max_transforms)
            result = enumerator.Enumerate(mol)
            status = getattr(result, "status", None)
            if (
                str(status) != "Completed"
                and getattr(status, "name", None) != "Completed"
            ):
                raise TautomerEnumerationLimitError()
            return _clear_atom_maps(enumerator.PickCanonical(result))
        except TautomerEnumerationLimitError:
            raise
        except Exception:
            raise TautomerEnumerationLimitError() from None


def _safe_charge_parent(mol: Any) -> Any:
    with _quiet_rdkit():
        try:
            return _clear_atom_maps(rdMolStandardize.ChargeParent(mol))
        except Exception:
            raise ParentPolicyMismatchError() from None


def _safe_fragment_parent(mol: Any) -> Any:
    with _quiet_rdkit():
        try:
            return _clear_atom_maps(rdMolStandardize.FragmentParent(mol))
        except Exception:
            raise ParentPolicyMismatchError() from None


@dataclass(frozen=True, slots=True)
class ChemistryService:
    """Canonicalize validated source SMILES using one immutable policy."""

    policy: ChemistryPolicy = DEFAULT_POLICY

    def canonicalize(
        self,
        source_smiles: str,
        *,
        preparation_ph: float | None = None,
        created_at: datetime,
    ) -> CanonicalizationResult:

        runtime_version = _runtime_version()
        identity = self._parse_identity(source_smiles)
        organic = _organic_components(identity)
        if not organic:
            raise NoOrganicParentStructureError()
        if len(organic) > 1:
            raise AmbiguousParentStructureError()

        fragment_parent = _safe_fragment_parent(identity)
        try:
            parent_matches_component = _same_molecule(fragment_parent, organic[0])
        except Exception:
            raise ParentPolicyMismatchError() from None
        if not parent_matches_component:
            raise ParentPolicyMismatchError()
        charge_parent = _safe_charge_parent(fragment_parent)
        final_parent = _configured_tautomer(charge_parent, self.policy)
        try:
            with _quiet_rdkit():
                Chem.RemoveStereochemistry(final_parent)
                state_smiles = _canonical_smiles(identity, isomeric=True)
                parent_isomeric_smiles = _canonical_smiles(final_parent, isomeric=True)
                parent_smiles = _canonical_smiles(final_parent, isomeric=False)
                formula = cast(str, rdMolDescriptors.CalcMolFormula(final_parent))
                molecular_weight = cast(float, Descriptors.MolWt(final_parent))
        except Exception:
            raise ParentPolicyMismatchError() from None

        nonstereo_state = _clear_atom_maps(identity)
        try:
            with _quiet_rdkit():
                Chem.RemoveStereochemistry(nonstereo_state)
                nonstereo_state_smiles = _canonical_smiles(
                    nonstereo_state, isomeric=False
                )
        except Exception:
            raise ParentPolicyMismatchError() from None
        charge_parent_state = _safe_charge_parent(nonstereo_state)
        charge_parent_state_smiles = _canonical_smiles(
            charge_parent_state, isomeric=False
        )
        tautomer_parent_state = _configured_tautomer(charge_parent_state, self.policy)
        tautomer_parent_state_smiles = _canonical_smiles(
            tautomer_parent_state, isomeric=False
        )
        try:
            with _quiet_rdkit():
                formal_charge = cast(int, Chem.GetFormalCharge(identity))
        except Exception:
            raise ParentPolicyMismatchError() from None

        state_inchikey, parent_inchikey, warnings = self._inchi_values(
            identity, final_parent
        )
        inchi_version = _inchi_library_version()
        try:
            compound = Compound(
                id=self._new_id(),
                canonical_smiles=parent_smiles,
                isomeric_smiles=parent_isomeric_smiles,
                inchikey=parent_inchikey,
                formula=formula,
                molecular_weight=molecular_weight,
                structure_hash=parent_hash(self.policy, parent_isomeric_smiles),
                chemistry_policy_id=self.policy.policy_id,
                rdkit_version=runtime_version,
                inchi_version=inchi_version,
                created_at=created_at,
            )
            state = MolecularState(
                compound_id=compound.id,
                state_smiles=state_smiles,
                state_inchikey=state_inchikey,
                formal_charge=formal_charge,
                stereochemistry_signature=hash_payload(
                    self.policy.stereo_signature_prefix, state_smiles
                ),
                protonation_signature=hash_payload(
                    self.policy.protonation_signature_prefix,
                    "charge="
                    + str(formal_charge)
                    + "\0"
                    + nonstereo_state_smiles
                    + "\0"
                    + charge_parent_state_smiles,
                ),
                tautomer_signature=hash_payload(
                    self.policy.tautomer_signature_prefix,
                    tautomer_parent_state_smiles,
                ),
                state_hash=state_hash(self.policy, state_smiles),
                chemistry_policy_id=self.policy.policy_id,
                rdkit_version=runtime_version,
                inchi_version=inchi_version,
                preparation_ph=preparation_ph,
            )
            return CanonicalizationResult(
                source_smiles=source_smiles,
                compound=compound,
                molecular_state=state,
                chemistry_policy_id=self.policy.policy_id,
                warnings=tuple(warnings),
            )
        except Exception:
            raise ParentPolicyMismatchError() from None

    @staticmethod
    def _new_id() -> str:
        from fidelichem.domain.ids import new_id

        return new_id()

    @staticmethod
    def _parse_identity(source_smiles: str) -> Any:
        if (
            not isinstance(source_smiles, str)
            or not source_smiles.strip()
            or "\x00" in source_smiles
            or len(source_smiles) > _MAX_SOURCE_CODEPOINTS
        ):
            raise InvalidStructureError()
        try:
            with _quiet_rdkit():
                molecule = cast(Any, Chem.MolFromSmiles(source_smiles, sanitize=True))
                if molecule is None:
                    raise ValueError
                Chem.SanitizeMol(molecule)
                identity = _clear_atom_maps(molecule)
                if identity.GetNumAtoms() > _MAX_ATOMS:
                    raise ValueError
                return identity
        except InvalidStructureError:
            raise
        except Exception:
            raise InvalidStructureError() from None

    @staticmethod
    def _inchi_values(
        identity: Chem.Mol, parent: Chem.Mol
    ) -> tuple[str | None, str | None, list[ChemistryWarning]]:
        with _quiet_rdkit():
            state_key = _inchi_key(identity)
            parent_key = _inchi_key(parent)
        warnings: list[ChemistryWarning] = []
        if state_key is None or parent_key is None:
            warnings.append(
                ChemistryWarning(
                    code=ChemistryWarningCode.INCHI_UNAVAILABLE,
                    message="InChI generation unavailable",
                )
            )
        return state_key, parent_key, warnings


__all__ = ["ChemistryService"]
