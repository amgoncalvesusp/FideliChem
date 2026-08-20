# FideliChem Phase 2 Chemistry and Identity Resolver Design

## Status and dependency gate

**Status: queued. Do not implement until the Phase 1 Terra gate is GO.**

This specification narrows Phase 2 of `FideliChem_PLANO_CODEX.md`. Phase 1 is
the authoritative versioned storage foundation. This phase adds only a new
Alembic revision after Phase 1 project, lifecycle, provenance, and audit gates
are complete.

## Goal and scope

Deliver a deterministic, auditable molecular-identity core that normalizes
SMILES through an isolated RDKit service, distinguishes chemical compound
families from explicit molecular states, preserves aliases, and reports
uncertainty rather than silently merging records.

Included:

- RDKit dependency and a bounded chemistry service;
- frozen `Compound`, `MolecularState`, `Alias`, and
  `IdentityResolution` values;
- Alembic schema, private ORM rows, and transaction-bound repositories;
- a pure matching engine and immutable ambiguity reports; and
- an explicit, reversible and audited resolution service.

Excluded: adapters, Import Manager, `ImportBundle`, generic-table parsing,
targets/poses/scores/MD, GUI confirmation, molecule drawing, fingerprints,
tautomer/protomer enumeration, and any external scientific execution. Future
adapters preserve raw source data and pass claims to this core; they neither
import RDKit nor write SQL.

## Runtime boundary and safeguards

Add runtime `rdkit>=2026.3.4,<2026.4`; `uv.lock` fixes the exact build. This
range has CPython 3.12 Windows x64 and Linux x64 wheels, the supported package
targets. Add `hypothesis>=6.0` only to the development dependency group.

Only `src/fidelichem/chemistry/**` may import `rdkit`. A static repository
test rejects direct RDKit imports from every other production package. The
public identity resolver receives frozen values and protocols, never an RDKit
`Mol`.

Before RDKit parses a SMILES, reject blank input, a NUL byte, more than 10,000
Unicode code points, and a parsed molecule with more than 2,000 atoms. Convert
RDKit parsing, sanitization, and InChI failures to typed public errors that do
not echo the complete untrusted input. The service accepts multiple components
and never selects a largest fragment or removes a salt from the exact state.
No input is executed; no shell, network, pickle, `eval`, or secret is used.

## Identity policy

### Exact state

`MolecularState` is the sanitized exact molecule. Its `state_smiles` comes
from `Chem.MolToSmiles(exact, canonical=True, isomericSmiles=True)` and
retains the supplied stereo, charge, tautomer, and disconnected components.

`state_hash` is SHA-256 over these UTF-8 bytes:

    fidelichem.molecular-state.v1\0<state-smiles>

The policy version is therefore part of the hash payload. Equality of this hash
is the sole automatic structural equality in the resolver. A generated full
InChIKey is preserved as evidence but is not a unique state key.

`formal_charge` is RDKit's net formal charge. Stereo, protonation, and
tautomer signatures are deterministic, versioned chemistry-service descriptors
for QC and display only; resolver equality never relies on an individual
descriptor.

### Compound family

`Compound` is a chemical family, not a source filename, pose, or first state
seen. Derive it from a copy of the exact sanitized molecule through this fixed
policy pipeline:

    FragmentParent -> ChargeParent -> TautomerParent -> RemoveStereochemistry

This pipeline is grouping metadata only: it never changes `state_smiles` or
the validated original input retained in a canonicalization result. An exact
mixture or salt is therefore preserved even when a parent representation
groups it.

Deterministic public semantics are:

- `canonical_smiles`: non-isomeric canonical SMILES of the final parent;
- `isomeric_smiles`: isomeric canonical SMILES of that same final parent after
  stereo removal. It is normally equal to `canonical_smiles`, and is never a
  representative state chosen by import order;
- `inchikey`, formula, and molecular weight: calculated from that parent; and
- `structure_hash`: SHA-256 of
  `fidelichem.compound-parent.v1\0<parent-isomeric-smiles>`.

The parent hash is unique in the project. A novel exact state with one known
parent hash is a candidate new state for that compound, not an exact-state
match.

### InChIKey and missing structure

InChIKey generation occurs only after successful sanitization. Empty or
unavailable output raises `InchiUnavailableError`; no empty/fabricated key is
stored. An external InChIKey with no internally normalized SMILES can enumerate
candidates but cannot authorize an automatic merge. Missing SMILES remains
`None`; aliases, names, formulae, and InChIKeys never become guessed
structures or zero-valued properties.

## Public values

All values use the existing frozen `DomainModel`, canonical UUID4 IDs, aware
UTC timestamps, and `extra="forbid"`.

    class Compound(DomainModel):
        id: OpaqueId = Field(default_factory=new_id)
        canonical_smiles: NonBlankText
        isomeric_smiles: NonBlankText
        inchikey: InchiKey
        formula: NonBlankText
        molecular_weight: FiniteFloat = Field(gt=0)
        structure_hash: Sha256Digest
        created_at: UtcTimestamp

    class MolecularState(DomainModel):
        id: OpaqueId = Field(default_factory=new_id)
        compound_id: OpaqueId
        state_smiles: NonBlankText
        state_inchikey: InchiKey
        formal_charge: int
        stereochemistry_signature: NonBlankText
        protonation_signature: NonBlankText
        tautomer_signature: NonBlankText
        state_hash: Sha256Digest
        preparation_ph: FiniteFloat | None = Field(default=None, ge=0, le=14)

    class Alias(DomainModel):
        id: OpaqueId = Field(default_factory=new_id)
        source_system: SourceSystem
        source_value: NonBlankText
        import_batch_id: OpaqueId
        created_at: UtcTimestamp

    class IdentityResolution(DomainModel):
        id: OpaqueId = Field(default_factory=new_id)
        alias_id: OpaqueId
        decision: IdentityDecision
        compound_id: OpaqueId | None
        molecular_state_id: OpaqueId | None
        supersedes_id: OpaqueId | None
        decided_at: UtcTimestamp
        actor_kind: ActorKind
        actor_id: str | None
        rationale: str | None

`SourceSystem` is lower-case ASCII matching
`[a-z0-9][a-z0-9._-]{0,127}`. `source_value` preserves case and Unicode but
rejects NUL, blank-only text, and values longer than 1,024 characters.

`IdentityDecision` is `confirmed`, `reassigned`, or `retracted`.
Confirmed requires a compound and no predecessor; reassigned requires a
compound and a predecessor; retracted requires null targets and a predecessor.
A non-null state must belong to the selected compound. Decisions are immutable;
a later row supersedes an earlier decision.

`Alias` is an immutable source identifier. `IdentityResolution` carries its
mutable-in-time association as an append-only chain, so raw evidence is never
rewritten. The active resolved-alias projection supplies the compound/state
relationship described in the master plan.

The chemistry package also exposes:

    class CanonicalizationResult(DomainModel):
        source_smiles: str
        compound: Compound
        molecular_state: MolecularState
        chemistry_policy: str

    class IdentityClaim(DomainModel):
        source_system: SourceSystem | None
        source_value: str | None
        smiles: str | None
        inchikey: InchiKey | None
        import_batch_id: OpaqueId | None

`source_smiles` is the validated unmodified input so future adapters can retain
it in provenance. It is not a substitute for a source artifact.

## Pure resolver

The resolver takes `IdentityClaim` plus a read-only `IdentityIndex` protocol
and returns a frozen `ResolutionReport`. It has no SQLAlchemy/repository
import, write method, audit side effect, or database dependency.

    class ResolutionKind(StrEnum):
        EXACT_STATE = "exact_state"
        NEW_STATE_FOR_COMPOUND = "new_state_for_compound"
        ALIAS_ONLY = "alias_only"
        AMBIGUOUS = "ambiguous"
        CONFLICT = "conflict"
        UNRESOLVED = "unresolved"

Candidates sort by compound ID then molecular-state ID, never by external name
or row order. Rules:

1. Valid SMILES is canonicalized first. A unique equal `state_hash` is
   `EXACT_STATE`.
2. With no exact state and one equal parent hash, return
   `NEW_STATE_FOR_COMPOUND`; do not write the state.
3. Structure evidence and alias evidence targeting different identities yield
   `CONFLICT`.
4. Without SMILES, InChIKey/alias evidence only produces `ALIAS_ONLY` or
   `AMBIGUOUS`, never automatic assignment.
5. No usable evidence produces `UNRESOLVED`.

The only Phase 2 mutating API is `IdentityService.confirm`, `.reassign`, and
`.retract`. It validates the selected target, appends the alias/resolution
decision and exactly one canonical `AuditEvent` in a single unit of work.

## Storage and rollback

Migration `0002_chemistry_identity` creates append-only tables with named
constraints and `ON DELETE RESTRICT` FKs:

- `compound`: UUID and unique parent `structure_hash`;
- `molecular_state`: UUID, `compound_id`, and unique exact `state_hash`;
- `alias`: UUID, source system/value, `import_batch_id`, and unique
  `(import_batch_id, source_system, source_value)`; and
- `identity_resolution`: UUID, alias/target FKs, nullable self-FK
  `supersedes_id`, and unique `supersedes_id` to prevent forks.

Checks enforce hash/UTC/text/decision/pH constraints. A trigger checks state
ownership by selected compound. Triggers reject update/delete/replacement on
all four tables. No cascade is introduced.

The identity catalogue may survive a batch rollback like raw artifacts and
audit history. Visibility of sourced identity evidence is determined by active
aliases/resolutions whose import batch is not logically rolled back; rollback
does not physically erase molecular information.

## Test and acceptance requirements

Use RED-GREEN-REFACTOR for equivalent SMILES, stereo/protomer/tautomer state
separation, exact mixtures, invalid and resource-bounded inputs, InChI failure,
InChIKey-only/missing-SMILES/alias-only/conflict cases, deterministic ordering,
schema migration from populated `0001`, direct SQL immutability, corrupt rows,
atomic decision/audit failures, reassignment/retraction, and project reopen.
Hypothesis may produce bounded alias/claim combinations but never unbounded
SMILES sent to RDKit.

Phase 2 passes only with 80%+ branch coverage globally and for new modules,
safe populated-Phase-1 migration, no silent ambiguous merge, pure resolver,
append-only reversible decisions, full verification gate, and a Terra xhigh
review with no unresolved Critical or Important finding.
