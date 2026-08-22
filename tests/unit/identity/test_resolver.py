from __future__ import annotations

import ast
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import pytest

from fidelichem.domain.chemistry import (
    CanonicalizationResult,
    Compound,
    IdentityClaim,
    MolecularState,
)
from fidelichem.identity.models import (
    CatalogAction,
    EvidenceKind,
    ResolutionCandidate,
    ResolutionKind,
    ResolutionReason,
)
from fidelichem.identity.resolver import IdentityResolver

NOW = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)
COMPOUND_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
COMPOUND_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
STATE_A = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
STATE_B = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
RESOLUTION_A = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"
INCHI_A = "LFQSCWFLJHTTHZ-UHFFFAOYSA-N"
INCHI_B = "VNWKTOKETHGBQD-UHFFFAOYSA-N"


def _result(
    *,
    compound_id: str = COMPOUND_A,
    state_id: str = STATE_A,
    state_hash: str = "a" * 64,
    parent_hash: str = "b" * 64,
    state_inchikey: str | None = INCHI_A,
    compound_inchikey: str | None = INCHI_A,
    source_smiles: str = "CCO",
) -> CanonicalizationResult:
    compound = Compound(
        id=compound_id,
        canonical_smiles="CCO",
        isomeric_smiles="CCO",
        inchikey=compound_inchikey,
        formula="C2H6O",
        molecular_weight=46.069,
        structure_hash=parent_hash,
        chemistry_policy_id="fidelichem.rdkit-identity.v1",
        rdkit_version="2026.3.4",
        inchi_version="1.0.0",
        created_at=NOW,
    )
    state = MolecularState(
        id=state_id,
        compound_id=compound_id,
        state_smiles=source_smiles,
        state_inchikey=state_inchikey,
        formal_charge=0,
        stereochemistry_signature="stereo",
        protonation_signature="charge",
        tautomer_signature="tautomer",
        state_hash=state_hash,
        chemistry_policy_id="fidelichem.rdkit-identity.v1",
        rdkit_version="2026.3.4",
        inchi_version="1.0.0",
    )
    return CanonicalizationResult(
        source_smiles=source_smiles,
        compound=compound,
        molecular_state=state,
        chemistry_policy_id="fidelichem.rdkit-identity.v1",
    )


def _claim(
    *,
    smiles: str | None = "CCO",
    inchikey: str | None = None,
    source_system: str | None = None,
    source_value: str | None = None,
    import_batch_id: str | None = None,
) -> IdentityClaim:
    return IdentityClaim(
        smiles=smiles,
        inchikey=inchikey,
        source_system=source_system,
        source_value=source_value,
        import_batch_id=import_batch_id,
    )


@dataclass(frozen=True)
class FakeIndex:
    states: dict[str, tuple[ResolutionCandidate, ...]] = field(default_factory=dict)
    parents: dict[str, tuple[ResolutionCandidate, ...]] = field(default_factory=dict)
    inchis: dict[str, tuple[ResolutionCandidate, ...]] = field(default_factory=dict)
    aliases: dict[tuple[str, str], tuple[ResolutionCandidate, ...]] = field(
        default_factory=dict
    )

    def catalog_by_state_hash(self, state_hash: str) -> tuple[ResolutionCandidate, ...]:
        return self.states.get(state_hash, ())

    def catalog_by_parent_hash(
        self, parent_hash: str
    ) -> tuple[ResolutionCandidate, ...]:
        return self.parents.get(parent_hash, ())

    def catalog_by_generated_inchikey(
        self, inchikey: str
    ) -> tuple[ResolutionCandidate, ...]:
        return self.inchis.get(inchikey, ())

    def active_by_alias(
        self, source_system: str, source_value: str
    ) -> tuple[ResolutionCandidate, ...]:
        return self.aliases.get((source_system, source_value), ())


@dataclass(frozen=True)
class SpyIndex(FakeIndex):
    calls: list[tuple[str, str]] = field(default_factory=list)

    def catalog_by_state_hash(self, state_hash: str) -> tuple[ResolutionCandidate, ...]:
        self.calls.append(("state", state_hash))
        return super().catalog_by_state_hash(state_hash)

    def catalog_by_parent_hash(
        self, parent_hash: str
    ) -> tuple[ResolutionCandidate, ...]:
        self.calls.append(("parent", parent_hash))
        return super().catalog_by_parent_hash(parent_hash)

    def catalog_by_generated_inchikey(
        self, inchikey: str
    ) -> tuple[ResolutionCandidate, ...]:
        self.calls.append(("inchi", inchikey))
        return super().catalog_by_generated_inchikey(inchikey)

    def active_by_alias(
        self, source_system: str, source_value: str
    ) -> tuple[ResolutionCandidate, ...]:
        self.calls.append(("alias", source_system + ":" + source_value))
        return super().active_by_alias(source_system, source_value)


def _candidate(
    compound_id: str = COMPOUND_A,
    state_id: str | None = STATE_A,
    *,
    resolution_id: str | None = RESOLUTION_A,
    evidence: tuple[EvidenceKind, ...] = (EvidenceKind.CATALOG_STATE,),
    dormant: bool = False,
) -> ResolutionCandidate:
    return ResolutionCandidate(
        compound_id=compound_id,
        molecular_state_id=state_id,
        resolution_id=resolution_id,
        evidence=evidence,
        catalog_dormant=dormant,
    )


def test_exact_state_has_reuse_state_and_preserves_dormancy() -> None:
    result = _result()
    index = FakeIndex(
        states={"a" * 64: (_candidate(dormant=True),)},
        inchis={INCHI_A: (_candidate(dormant=True),)},
    )
    report = IdentityResolver().resolve(result, _claim(), index)
    assert report.kind is ResolutionKind.EXACT_STATE
    assert report.reason is ResolutionReason.EXACT_STATE
    assert report.catalog_action is CatalogAction.REUSE_STATE
    assert report.catalog_match_dormant is True
    assert report.candidates[0].catalog_dormant is True


def test_new_state_reuses_one_parent_but_not_sibling_state() -> None:
    result = _result(state_hash="c" * 64)
    parent = _candidate(state_id=None, evidence=(EvidenceKind.CATALOG_PARENT,))
    sibling = _candidate(state_id=STATE_B, evidence=(EvidenceKind.CATALOG_STATE,))
    report = IdentityResolver().resolve(
        result,
        _claim(),
        FakeIndex(states={"c" * 64: ()}, parents={"b" * 64: (parent,)}, inchis={}),
    )
    assert report.kind is ResolutionKind.NEW_STATE
    assert report.catalog_action is CatalogAction.REUSE_COMPOUND
    assert report.candidates[0].molecular_state_id is None
    assert sibling not in report.candidates


def test_empty_index_returns_new_compound_without_persistence_fields() -> None:
    report = IdentityResolver().resolve(
        _result(),
        _claim(source_system=None, source_value=None),
        FakeIndex(),
    )
    assert report.kind is ResolutionKind.NEW_COMPOUND
    assert report.reason is ResolutionReason.NEW_COMPOUND
    assert report.catalog_action is CatalogAction.CREATE_COMPOUND


def test_state_signatures_do_not_weaken_exact_state_evidence() -> None:
    result = _result(state_hash="f" * 64)
    report = IdentityResolver().resolve(
        result,
        _claim(),
        FakeIndex(parents={"b" * 64: (_candidate(state_id=None),)}),
    )
    assert report.kind is ResolutionKind.NEW_STATE
    assert report.candidates[0].molecular_state_id is None


def test_result_none_requires_claim_without_smiles_and_resolves_alias_only() -> None:
    alias = _candidate(
        state_id=None,
        evidence=(EvidenceKind.ACTIVE_ALIAS,),
    )
    report = IdentityResolver().resolve(
        None,
        _claim(smiles=None, source_system="gold", source_value="ligand-1"),
        FakeIndex(aliases={("gold", "ligand-1"): (alias,)}),
    )
    assert report.kind is ResolutionKind.ALIAS_ONLY
    assert report.reason is ResolutionReason.ALIAS_ONLY
    assert report.catalog_action is CatalogAction.NONE


def test_external_inchi_only_claim_remains_unresolved_but_keeps_evidence() -> None:
    candidate = _candidate(
        state_id=None,
        evidence=(EvidenceKind.CATALOG_INCHI,),
    )
    report = IdentityResolver().resolve(
        None,
        _claim(smiles=None, inchikey=INCHI_A),
        FakeIndex(inchis={INCHI_A: (candidate,)}),
    )
    assert report.kind is ResolutionKind.UNRESOLVED
    assert report.candidates[0].evidence == (EvidenceKind.CATALOG_INCHI,)


def test_result_none_keeps_alias_and_supplied_inchi_weak_evidence() -> None:
    alias = _candidate(COMPOUND_A, None, evidence=(EvidenceKind.ACTIVE_ALIAS,))
    external = _candidate(
        COMPOUND_B,
        None,
        evidence=(EvidenceKind.CATALOG_INCHI,),
    )
    report = IdentityResolver().resolve(
        None,
        _claim(smiles=None, inchikey=INCHI_B, source_system="gold", source_value="x"),
        FakeIndex(
            aliases={("gold", "x"): (alias,)},
            inchis={INCHI_B: (external,)},
        ),
    )
    assert report.kind is ResolutionKind.ALIAS_ONLY
    assert {candidate.compound_id for candidate in report.candidates} == {
        COMPOUND_A,
        COMPOUND_B,
    }


def test_result_none_smiles_boundary_precedes_all_index_reads() -> None:
    index = SpyIndex(
        inchis={INCHI_B: (_candidate(COMPOUND_B, None),)},
        aliases={("gold", "x"): (_candidate(),)},
    )
    with pytest.raises(ValueError):
        IdentityResolver().resolve(
            None,
            _claim(
                smiles="CCO",
                inchikey=INCHI_B,
                source_system="gold",
                source_value="x",
            ),
            index,
        )
    assert index.calls == []


def test_import_batch_without_source_pair_is_resolver_usable() -> None:
    report = IdentityResolver().resolve(
        _result(),
        _claim(import_batch_id="ffffffff-ffff-4fff-8fff-ffffffffffff"),
        FakeIndex(),
    )
    assert report.kind is ResolutionKind.NEW_COMPOUND


def test_multiple_alias_targets_are_ambiguous() -> None:
    aliases = (
        _candidate(COMPOUND_A, None, evidence=(EvidenceKind.ACTIVE_ALIAS,)),
        _candidate(COMPOUND_B, None, evidence=(EvidenceKind.ACTIVE_ALIAS,)),
    )
    report = IdentityResolver().resolve(
        None,
        _claim(smiles=None, source_system="gold", source_value="ambiguous"),
        FakeIndex(aliases={("gold", "ambiguous"): aliases}),
    )
    assert report.kind is ResolutionKind.AMBIGUOUS
    assert report.reason is ResolutionReason.AMBIGUOUS_ALIAS


def test_result_none_with_smiles_and_source_mismatch_is_rejected() -> None:
    with pytest.raises(ValueError):
        IdentityResolver().resolve(None, _claim(smiles="CCO"), FakeIndex())


def test_result_source_smiles_must_equal_claim_exactly() -> None:
    with pytest.raises(ValueError):
        IdentityResolver().resolve(
            _result(source_smiles="CCO"), _claim(smiles="CCO "), FakeIndex()
        )


def test_external_inchi_conflict_is_not_auto_merged() -> None:
    report = IdentityResolver().resolve(
        _result(state_inchikey=INCHI_A),
        _claim(inchikey=INCHI_B),
        FakeIndex(),
    )
    assert report.kind is ResolutionKind.CONFLICT
    assert report.reason is ResolutionReason.CONFLICTING_EVIDENCE
    assert report.catalog_action is CatalogAction.NONE


def test_external_inchi_conflict_reports_all_structural_and_inchi_evidence() -> None:
    state = _candidate(COMPOUND_A, STATE_A, evidence=(EvidenceKind.CATALOG_STATE,))
    parent = _candidate(COMPOUND_A, None, evidence=(EvidenceKind.CATALOG_PARENT,))
    generated = _candidate(
        COMPOUND_A,
        STATE_A,
        evidence=(EvidenceKind.CATALOG_INCHI,),
    )
    supplied = _candidate(
        COMPOUND_B,
        None,
        evidence=(EvidenceKind.CATALOG_INCHI,),
    )
    report = IdentityResolver().resolve(
        _result(),
        _claim(inchikey=INCHI_B),
        FakeIndex(
            states={"a" * 64: (state,)},
            parents={"b" * 64: (parent,)},
            inchis={INCHI_A: (generated,), INCHI_B: (supplied,)},
        ),
    )
    assert report.kind is ResolutionKind.CONFLICT
    assert {
        (candidate.compound_id, candidate.molecular_state_id)
        for candidate in report.candidates
    } == {(COMPOUND_A, STATE_A), (COMPOUND_A, None), (COMPOUND_B, None)}
    evidence = {
        item
        for candidate in report.candidates
        for item in candidate.evidence
    }
    assert EvidenceKind.CATALOG_STATE in evidence
    assert EvidenceKind.CATALOG_PARENT in evidence
    assert EvidenceKind.CATALOG_INCHI in evidence


def test_supplied_inchi_is_queried_once_and_reused() -> None:
    index = SpyIndex(inchis={INCHI_B: (_candidate(COMPOUND_B, None),)})
    IdentityResolver().resolve(
        _result(state_inchikey=INCHI_B, compound_inchikey=None),
        _claim(inchikey=INCHI_B),
        index,
    )
    assert [call for call in index.calls if call == ("inchi", INCHI_B)] == [
        ("inchi", INCHI_B)
    ]


def test_structural_and_alias_targets_disagree_as_conflict() -> None:
    report = IdentityResolver().resolve(
        _result(),
        _claim(source_system="gold", source_value="alias"),
        FakeIndex(
            states={"a" * 64: (_candidate(COMPOUND_A),)},
            aliases={
                ("gold", "alias"): (
                    _candidate(COMPOUND_B, None, evidence=(EvidenceKind.ACTIVE_ALIAS,)),
                )
            },
        ),
    )
    assert report.kind is ResolutionKind.CONFLICT
    assert report.reason is ResolutionReason.CONFLICTING_EVIDENCE


def test_exact_state_and_alias_sibling_state_conflict_even_for_same_compound() -> None:
    report = IdentityResolver().resolve(
        _result(),
        _claim(source_system="gold", source_value="sibling"),
        FakeIndex(
            states={"a" * 64: (_candidate(COMPOUND_A, STATE_A),)},
            aliases={
                ("gold", "sibling"): (
                    _candidate(
                        COMPOUND_A,
                        STATE_B,
                        evidence=(EvidenceKind.ACTIVE_ALIAS,),
                    ),
                )
            },
        ),
    )
    assert report.kind is ResolutionKind.CONFLICT


def test_new_state_and_alias_sibling_state_conflict_under_same_parent() -> None:
    report = IdentityResolver().resolve(
        _result(state_hash="f" * 64),
        _claim(source_system="gold", source_value="sibling-parent"),
        FakeIndex(
            parents={"b" * 64: (_candidate(COMPOUND_A, None),)},
            aliases={
                ("gold", "sibling-parent"): (
                    _candidate(
                        COMPOUND_A,
                        STATE_B,
                        evidence=(EvidenceKind.ACTIVE_ALIAS,),
                    ),
                )
            },
        ),
    )
    assert report.kind is ResolutionKind.CONFLICT


def test_invalid_claim_or_result_is_rejected_before_index_access() -> None:
    index = SpyIndex()
    with pytest.raises(TypeError):
        IdentityResolver().resolve(None, object(), index)  # type: ignore[arg-type]
    assert index.calls == []
    with pytest.raises(TypeError):
        IdentityResolver().resolve(object(), _claim(), index)  # type: ignore[arg-type]
    assert index.calls == []
    malformed = CanonicalizationResult.model_construct(source_smiles="CCO")
    with pytest.raises(ValueError):
        IdentityResolver().resolve(malformed, _claim(), index)
    assert index.calls == []


def test_all_evidence_surfaces_are_queried_and_deduplicated() -> None:
    index = SpyIndex()
    IdentityResolver().resolve(
        _result(),
        _claim(inchikey=INCHI_B, source_system="gold", source_value="all"),
        index,
    )
    assert ("alias", "gold:all") in index.calls
    assert ("state", "a" * 64) in index.calls
    assert ("parent", "b" * 64) in index.calls
    assert ("inchi", INCHI_A) in index.calls
    assert ("inchi", INCHI_B) in index.calls


def test_inchi_candidates_are_evidence_only_and_deterministic() -> None:
    candidates = (
        _candidate(COMPOUND_B, None, evidence=(EvidenceKind.CATALOG_INCHI,)),
        _candidate(COMPOUND_A, STATE_A, evidence=(EvidenceKind.CATALOG_INCHI,)),
    )
    report = IdentityResolver().resolve(
        _result(state_hash="e" * 64, parent_hash="f" * 64),
        _claim(),
        FakeIndex(inchis={INCHI_A: candidates}),
    )
    assert report.kind is ResolutionKind.NEW_COMPOUND
    assert report.catalog_action is CatalogAction.CREATE_COMPOUND
    assert [candidate.compound_id for candidate in report.candidates] == [
        COMPOUND_A,
        COMPOUND_B,
    ]
    assert EvidenceKind.CATALOG_INCHI in report.candidates[0].evidence


def test_compound_only_alias_same_parent_does_not_conflict_with_exact_state() -> None:
    report = IdentityResolver().resolve(
        _result(),
        _claim(source_system="gold", source_value="compound-alias"),
        FakeIndex(
            states={"a" * 64: (_candidate(COMPOUND_A, STATE_A, dormant=True),)},
            aliases={
                ("gold", "compound-alias"): (
                    _candidate(
                        COMPOUND_A,
                        None,
                        evidence=(EvidenceKind.ACTIVE_ALIAS,),
                    ),
                )
            },
        ),
    )
    assert report.kind is ResolutionKind.EXACT_STATE
    assert report.catalog_match_dormant is True


def test_static_resolver_is_pure_and_has_no_write_methods() -> None:
    path = Path(__file__).resolve().parents[3] / "src/fidelichem/identity/resolver.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = [
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    ]
    imports.extend(
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    )
    assert all(
        "storage" not in module and "sqlalchemy" not in module for module in imports
    )
    assert "sqlalchemy" not in source.lower()
    assert "rdkit" not in source.lower()
    dynamic_imports = {
        (
            "name",
            node.func.id,
        )
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"__import__", "import_module"}
    }
    dynamic_imports.update(
        (
            "attribute",
            node.func.attr,
        )
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"__import__", "import_module"}
    )
    assert dynamic_imports == set()
    mutation_calls = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr
        in {
            "add",
            "save",
            "commit",
            "flush",
            "write",
            "delete",
            "execute",
            "setattr",
            "append",
            "extend",
            "update",
            "__setitem__",
        }
    }
    assert mutation_calls == set()
    assert not any(
        isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Subscript) for target in node.targets)
        for node in ast.walk(tree)
    )
    resolver = next(node for node in tree.body if isinstance(node, ast.ClassDef))
    methods = {
        node.name
        for node in resolver.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert not methods.intersection({"add", "save", "commit", "write", "delete"})
