# ADR 0002: Compound families and exact molecular states

- Status: Accepted
- Date: 2026-08-22

## Context

Identity resolution must distinguish a chemical family from the exact state
reported by an input source. A source may include atom maps, salts, charge,
stereochemistry, tautomeric form, or disconnected counterions. Those details
must remain available for provenance and exact-state matching without allowing
an import-order-dependent parent choice or a silent co-crystal merge.

## Decision

`Compound` is the immutable chemical-family catalog record. `MolecularState`
is an exact, map-cleared state belonging to one compound. Equality used for an
automatic exact match is the versioned `state_hash`; parent equality only
authorizes the `NEW_STATE` outcome and never replaces an exact state.

Canonicalization preserves the validated `source_smiles` byte-for-character
and makes a separate identity copy. Atom-map numbers are cleared on that copy
before state serialization, descriptors, InChI, or hashes. The exact state
retains stereo, charge, tautomer, and every disconnected component. The
compound parent pipeline is:

```text
FragmentParent -> ChargeParent -> bounded ConfiguredTautomerParent
                -> RemoveStereochemistry
```

The configured tautomer enumerator is limited to 128 tautomers and 256
transforms. The result status is inspected and only `Completed` is accepted;
any other status raises the typed incomplete-enumeration error before durable
identity rows can be written.

The parent policy is conservative:

- one organic component plus inorganic counterions uses the sole
  carbon-containing component as the parent and keeps the counterions in the
  exact state;
- two or more organic components (including co-crystals and mixtures) are
  rejected as `CHEMISTRY_PARENT_MULTIORGANIC`;
- a structure with no organic component is rejected rather than assigned a
  fabricated parent.

`Compound.formula` is `CalcMolFormula(parent)`. `Compound.molecular_weight`
is the unrounded `Descriptors.MolWt(parent)` value in g/mol (numerically
Da-equivalent). `Compound.structure_hash` and `MolecularState.state_hash` are
SHA-256 values with the frozen policy-specific prefixes. RDKit version,
policy ID, and nullable InChI library version are persisted with both
records. InChIKey is optional evidence: an unavailable or invalid key is
stored as `NULL`, and `inchi_unavailable` is carried as a chemistry warning.

Changing a transformation, descriptor algorithm, limit, or hash payload
requires a new chemistry policy ID and new hash prefixes. Existing catalog
rows are not recomputed under a new policy.

## Consequences

Different protonation, stereochemical, tautomeric, or component-preserving
states can be represented under one immutable parent without conflating their
identity. A new exact state can reuse a parent compound, while exact-state
reuse remains deterministic. Salt handling supports ordinary one-organic
salts but intentionally requires human policy for co-crystals and other
multi-organic structures.

This ADR does not define adapters, target/pose identity, fingerprints,
unbounded tautomer enumeration, docking/MD execution, or GUI behavior. Those
consumers must use the canonical bundle and must not import RDKit outside the
chemistry boundary.

## Evidence

The project workflow regression demonstrates map stripping, one-organic salt
handling, exact-state reuse, parent-only `NEW_STATE`, nullable InChI warning
audit, multi-organic rejection, and incomplete-tautomer rejection in
`tests/integration/identity/test_phase2_workflow.py`. Focused chemistry tests
also cover the frozen policy values, descriptor/hash semantics, atom maps,
limits, and optional InChI behavior.
