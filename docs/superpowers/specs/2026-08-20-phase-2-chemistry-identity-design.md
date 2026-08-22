# FideliChem Phase 2 Chemistry and Identity Resolver Design

## Status and dependency gate

**Status: queued. Do not implement until the Phase 1 Terra gate is GO.**

This specification narrows Phase 2 of FideliChem_PLANO_CODEX.md. Phase 1
remains the authoritative project, storage, lifecycle, provenance, and audit
foundation. Phase 2 adds only Alembic revision 0002 after the Phase 1 gate.

## Goal and scope

Deliver a deterministic, auditable molecular-identity core that normalizes
SMILES through an isolated RDKit service, separates a chemical compound family
from its explicit molecular states, keeps source aliases reversible, and
reports ambiguity rather than silently merging records.

Included:

- the exact RDKit runtime and frozen chemistry/identity public values;
- canonicalization, bounded parentization, InChI evidence, and versioned hashes;
- append-only identity schema, repositories, and a read-only database index;
- a pure resolver and immutable ambiguity reports; and
- one atomic claim-confirmation operation with a batch-correlated audit event,
  plus append-only reassignment, retraction, and restoration.

Excluded: adapters, Import Manager, ImportBundle, parsing tables, targets,
poses, scores, MD, GUI confirmation, molecule drawing, fingerprints,
enumeration beyond the bounded canonicalization policy, and external scientific
execution. Future adapters preserve raw input/provenance and call this core;
they never import RDKit or write SQL.

## Exact runtime, policy, and module boundary

Add the exact runtime dependency rdkit==2026.3.4. The lockfile contains the
selected wheels and hashes. Python remains 3.12. Add hypothesis>=6.0 only to
the development dependency group.

Only files under src/fidelichem/chemistry may import rdkit. A static AST test
fails if any other production package imports rdkit. The resolver receives
frozen values and protocols, never RDKit Mol values. Storage stores primitive
values and does not construct a chemistry object.

Canonicalization receives an explicit frozen ChemistryPolicy. The only initial
configured policy is:

    policy_id: fidelichem.rdkit-identity.v1
    state_hash_prefix: fidelichem.molecular-state.v1
    parent_hash_prefix: fidelichem.compound-parent.v1
    stereo_signature_prefix: fidelichem.stereochemistry.v1
    protonation_signature_prefix: fidelichem.protonation.v1
    tautomer_signature_prefix: fidelichem.tautomer.v1
    max_tautomers: 128
    max_transforms: 256

A change to any transformation, limits, descriptor algorithm, or hash payload
requires a new policy ID and new state/parent hash prefixes. Existing durable
rows are never recomputed or overwritten under a new policy.

Persist policy_id, rdkit_version, and nullable inchi_version on both Compound
and MolecularState. rdkit_version is the actual RDKit runtime version after a
semantic check that it is 2026.3.4. inchi_version is populated only when the
installed binding exposes it; otherwise it is null. It is never replaced by an
empty string.

## Resource, diagnostics, and source safeguards

Before parsing, reject blank input, NUL, more than 10,000 Unicode code points,
or a sanitized molecule with more than 2,000 atoms. Parser, sanitizer,
parentization, tautomer-limit, and InChI exceptions map to typed public errors
containing a stable diagnostic code but no source SMILES, file path, SQL, or
RDKit diagnostic. RDKit logging is disabled/captured locally during parsing so
untrusted source text does not reach application logs.

The original validated input is preserved byte-for-character in
CanonicalizationResult.source_smiles for a future adapter to record in
provenance. It is not used for database identity and it is not a substitute for
a SourceArtifact.

## Identity copies and exact state

After successful sanitization, the service makes an identity copy. It sets every
atom-map number on that copy to zero before *any* canonical serialization,
signature, InChIKey, formula, mass, or hash calculation. Atom maps and atom
renumbering are coordinate/import metadata, not chemistry identity. The raw
source input remains unchanged in CanonicalizationResult.source_smiles.

MolecularState.state_smiles is:

    Chem.MolToSmiles(identity_copy, canonical=True, isomericSmiles=True)

It retains the supplied stereo, charge, tautomer, and disconnected components,
except atom-map annotations. Its exact state hash is SHA-256 of UTF-8:

    fidelichem.molecular-state.v1\0<state-smiles>

Equality of state_hash is the sole automatic structural equality used by the
resolver.

The state descriptors have exact persisted formats, are versioned, and are for
QC/display only:

    stereochemistry_signature =
      fidelichem.stereochemistry.v1:<sha256(state-smiles)>

    protonation_signature =
      fidelichem.protonation.v1:<sha256(
        "charge=<net-charge>\0<nonstereo-state-smiles>\0<charge-parent-smiles>"
      )>

    tautomer_signature =
      fidelichem.tautomer.v1:<sha256(configured-tautomer-parent-smiles)>

Every sha256 token above is the lowercase 64-character hexadecimal encoding
of SHA-256 over the exact UTF-8 payload shown; angle brackets are notation and
are not serialized.

nonstereo-state-smiles is a map-cleared copy with stereochemistry removed and
without fragment, charge, or tautomer parentization. charge-parent-smiles is a
map-cleared nonstereo state after ChargeParent. configured-tautomer-parent-smiles
uses the bounded enumerator described below. These descriptors never authorize
a merge by themselves.

## Compound parent policy and salts/co-crystals

Compound represents a chemical family, not a source name, pose, or state first
seen. Starting from the map-cleared identity copy, its parent pipeline is:

    FragmentParent -> ChargeParent -> ConfiguredTautomerParent
                   -> RemoveStereochemistry

ConfiguredTautomerParent is a TautomerParent step implemented with a fresh
RDKit TautomerEnumerator configured with maxTautomers=128 and
maxTransforms=256. It must call Enumerate, inspect the returned enumeration
status, and continue only when status is Completed. It then selects the
canonical tautomer from that completed result. A status other than Completed
raises TautomerEnumerationLimitError with diagnostic code
CHEMISTRY_TAUTOMER_ENUMERATION_INCOMPLETE; no compound, state, alias,
resolution, or audit row may persist for that failed operation.

The exact state always keeps every component. Parentization has these
conservative representative rules:

1. One organic component plus any number of inorganic counterions: the sole
   carbon-containing component is the only permitted FragmentParent
   representative. Verify the FragmentParent output derives from that
   component; if RDKit selects anything else, fail with a typed parent-policy
   error. The discarded components remain in exact state and source provenance.
2. Two or more organic components: never choose a largest fragment, lexical
   winner, or RDKit tie winner. Raise AmbiguousParentStructureError with code
   CHEMISTRY_PARENT_MULTIORGANIC. A future importer must surface it as QC that
   requires a user-provided parent policy; this Phase 2 policy persists no
   incomplete identity.
3. No organic component after sanitation: raise
   CHEMISTRY_PARENT_NO_ORGANIC rather than fabricate a ligand family.

An organic component means a disconnected fragment containing at least one
carbon atom. This explicitly rejects automatic parentization of co-crystals,
two-ligand mixtures, and organic/organic ties while supporting normal
one-organic-fragment salts.

For a completed parent:

- Compound.canonical_smiles is its non-isomeric canonical SMILES.
- Compound.isomeric_smiles is isomeric canonical SMILES of the same final
  parent after stereo removal. It normally equals canonical_smiles and is
  never selected from an import-order-dependent state.
- Compound.formula is rdMolDescriptors.CalcMolFormula(parent).
- Compound.molecular_weight is Descriptors.MolWt(parent), the unrounded average
  molecular weight in g/mol; its numeric value is Da-equivalent. Do not round
  before persistence.
- Compound.structure_hash is SHA-256 of UTF-8
  fidelichem.compound-parent.v1\0<parent-isomeric-smiles>.

A new exact state with one equal parent hash is a candidate state for that
compound, never an exact-state match.

## InChI evidence and chemistry warnings

RDKit InChI generation is best-effort after sanitization. An available, valid
key is stored in Compound.inchikey and MolecularState.state_inchikey. An empty
key is invalid and is never persisted. Unavailable generation leaves both
values null and adds ChemistryWarning(code="inchi_unavailable") to the
canonicalization result.

During atomic claim confirmation, chemistry warning codes are recorded in
the same batch-correlated AuditEvent new_value_json. No extra half-committed
audit event is created. An external InChIKey-only claim may enumerate
candidates but never automatically merges. If a claim supplies SMILES and an
external InChIKey that differs from the service-generated non-null state key,
the resolver returns CONFLICT even if an alias appears to agree.

## Public contracts

All public values use the existing frozen DomainModel, canonical UUID4 IDs,
aware UTC timestamps, and extra="forbid".

    class Compound(DomainModel):
        id: OpaqueId = Field(default_factory=new_id)
        canonical_smiles: NonBlankText
        isomeric_smiles: NonBlankText
        inchikey: InchiKey | None
        formula: NonBlankText
        molecular_weight: FiniteFloat = Field(gt=0)
        structure_hash: Sha256Digest
        chemistry_policy_id: NonBlankText
        rdkit_version: NonBlankText
        inchi_version: NonBlankText | None
        created_at: UtcTimestamp

    class MolecularState(DomainModel):
        id: OpaqueId = Field(default_factory=new_id)
        compound_id: OpaqueId
        state_smiles: NonBlankText
        state_inchikey: InchiKey | None
        formal_charge: int
        stereochemistry_signature: NonBlankText
        protonation_signature: NonBlankText
        tautomer_signature: NonBlankText
        state_hash: Sha256Digest
        chemistry_policy_id: NonBlankText
        rdkit_version: NonBlankText
        inchi_version: NonBlankText | None
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

    class ChemistryWarning(DomainModel):
        code: ChemistryWarningCode
        message: str

    class CanonicalizationResult(DomainModel):
        source_smiles: str
        compound: Compound
        molecular_state: MolecularState
        chemistry_policy_id: NonBlankText
        warnings: tuple[ChemistryWarning, ...]

    class IdentityClaim(DomainModel):
        source_system: SourceSystem | None
        source_value: str | None
        smiles: str | None
        inchikey: InchiKey | None
        import_batch_id: OpaqueId | None

    class IdentitySelection(DomainModel):
        mode: SelectionMode  # existing_target | new_compound
        compound_id: OpaqueId | None
        molecular_state_id: OpaqueId | None

    class IdentityActor(DomainModel):
        kind: ActorKind  # user | system
        actor_id: str | None
        rationale: str | None

SourceSystem matches [a-z0-9][a-z0-9._-]{0,127}. source_value preserves case
and Unicode but rejects NUL, blank-only text, and values longer than 1,024
characters. IdentityClaim validates source_system and source_value as a
both-or-neither pair; when present they use the same length/NUL/blank rules as
Alias. import_batch_id may be null only for an in-memory pre-import claim;
every mutating confirmation rejects null before opening a write transaction.

IdentitySelection(existing_target) requires compound_id. Its optional state ID
must be the exact candidate state authorized by the report. SelectionMode
new_compound requires both IDs null and is valid only for NEW_COMPOUND. A
selection is valid only when it is a candidate listed in the immutable report,
the exact canonical target authorized by EXACT_STATE/NEW_STATE, or explicit
NEW_COMPOUND creation. Arbitrary compounds, sibling states, and report/target
substitution are rejected.

EXACT_STATE selection carries the report's compound and exact state IDs.
NEW_STATE selection carries the report's matched compound ID and a null state
ID because confirm_claim creates the canonical exact state. ALIAS_ONLY and
AMBIGUOUS carry a report-listed compound and null state. NEW_COMPOUND carries
no IDs.

IdentityActor(user) requires a nonblank actor_id of at most 128 characters.
IdentityActor(system) requires actor_id null. Rationale is null or nonblank and
at most 1,024 characters. System actors may confirm only unambiguous structural
EXACT_STATE, NEW_STATE, or NEW_COMPOUND reports. ALIAS_ONLY, AMBIGUOUS,
CONFLICT, reassignment, retraction, and restoration require a user actor and a
nonblank rationale. These values, not loose strings, are the service boundary.

IdentityDecision is confirmed, reassigned, retracted, or restored. Confirmed
has a compound target and no predecessor; reassigned has a compound target and a
non-null predecessor; retracted has null targets and a non-null predecessor. A
restored decision has compound target, optional owned state, a non-null
RETRACTED predecessor, a user actor, and nonblank rationale. RETRACTED may
follow only a targeted CONFIRMED, REASSIGNED, or RESTORED decision; therefore a
repeated retraction is invalid. A non-null state must belong to the selected
compound. Alias is raw immutable source evidence. Its current association is a
projection of append-only IdentityResolution rows, not an update to Alias.

## Resolver, authority, and persistent projection

The pure IdentityResolver takes CanonicalizationResult | None, IdentityClaim,
and a read-only IdentityIndex protocol. It imports no SQLAlchemy or storage
module, has no write method, and returns immutable ResolutionReport values.

Resolution kinds are EXACT_STATE, NEW_STATE, NEW_COMPOUND, ALIAS_ONLY,
AMBIGUOUS, CONFLICT, and UNRESOLVED. Candidates always sort by compound ID,
molecular-state ID (null last), then resolution ID (null last). Each candidate
contains an immutable, sorted tuple of evidence kinds from CATALOG_STATE,
CATALOG_PARENT, CATALOG_INCHI, and ACTIVE_ALIAS plus catalog_dormant: bool.
ResolutionReport also contains catalog_action (reuse_state, reuse_compound,
create_compound, or none) and catalog_match_dormant. These fields make dormant
catalog reuse explicit in both selection validation and audit.

A PersistentIdentityIndex is a separate storage-side read-only implementation
of IdentityIndex. Its constructor accepts the existing Phase 1 Engine or
SessionFactory; project workflows pass project.engine. It never assumes a
second project-level session-factory attribute. It runs only SELECT statements
against the project database, uses deterministic ORDER BY, and exposes two
deliberately different read surfaces.

Structural-catalog methods query immutable Compound and MolecularState rows
directly by state_hash, structure_hash, and generated InChIKey. They include
all catalog rows, even when their original alias was retracted, superseded, or
belongs to a rolled-back batch. A catalog candidate is dormant when no active
alias-resolution currently exposes its target.

The active-alias method uses a resolution projection that includes a row only
when:

- it has no successor row;
- its decision is not retracted (supersession is already excluded by the
  no-successor rule);
- its Alias.import_batch_id refers to a batch whose status is not rolled_back;
  and
- it has a non-null compound target.

Only active-alias lookup applies these lifecycle filters. Structural catalog
lookup never joins this projection. Thus an exact dormant state still yields
EXACT_STATE with catalog_action=reuse_state and catalog_match_dormant=true,
while its old alias remains invisible. Generated InChIKey catalog lookup is
candidate evidence only and never authorizes automatic merge. The resolver
remains pure because it depends on the protocol, not the storage
implementation.

The authority matrix is mandatory:

| Resolver result | Permitted atomic binding |
| --- | --- |
| EXACT_STATE | Require result. Reuse and bind only its catalog-matched exact state and owning compound, including a dormant match. Reject sibling state, different compound, or compound-only downgrade. |
| NEW_STATE | Require result. Reuse the exact matched parent Compound, materialize the result's exact state under it, and bind that state. Reject a sibling-state or compound-only selection. |
| NEW_COMPOUND | Require result and explicit new_compound selection. Atomically create the result Compound and exact state and bind it. A uniqueness race may reuse only the now-identical hashes, must be audited as reuse_after_race, and does not change the report kind. |
| ALIAS_ONLY / AMBIGUOUS | Result may be null. Require user actor, a candidate pre-existing target, and nonblank rationale. Bind the Compound only: molecular_state_id must be null. Never materialize result structures. |
| CONFLICT | Require a user actor, target listed in the report, and nonblank rationale; preserve both conflicting evidence and audit the override. Never accept an arbitrary target. |
| UNRESOLVED | Do not bind or invent an identity. |

A valid SMILES is canonicalized before resolution and its result is passed to
the resolver. A unique equal state hash yields EXACT_STATE. With no state and
one parent hash it yields NEW_STATE. With no state/parent match and no conflict
it yields NEW_COMPOUND, including in an empty project. The report records
whether any reused state/parent was dormant. If supplied external InChIKey
conflicts with generated structural evidence, or structural and active alias
evidence target different identities, it yields CONFLICT. Missing
SMILES/InChI/alias data is never converted into a molecule. result may be null
only when claim.smiles is null; when both are present, result.source_smiles must
equal claim.smiles exactly.

## Schema, concurrency, and rollback

Migration 0002_chemistry_identity creates compound, molecular_state, alias,
and identity_resolution with named constraints, indexes, and ON DELETE RESTRICT
FKs. Compound and state include chemistry_policy_id, rdkit_version, and nullable
inchi_version. Every identity record is append-only; triggers reject UPDATE,
DELETE, and replacement semantics.

Alias restores the named constraint uq_alias_batch_source over
UNIQUE(import_batch_id, source_system, source_value). Named SQL checks
ck_alias_source_system_format and ck_alias_source_value_bounds enforce
source_system length 1..128, lowercase slug alphabet and
alphanumeric first character; source_value length 1..1,024, nonblank after
trim, and no NUL. Application validation repeats the same rules. Concurrent
insertion of the same batch/source tuple has one winner; the loser transaction
rolls back and maps to safe AliasConflictError without an audit row.

identity_resolution must enforce its chain in the database, not only service
code:

- unique partial index on alias_id where supersedes_id IS NULL: at most one
  root resolution per alias;
- unique supersedes_id: exactly one successor per predecessor;
- self-FK on supersedes_id: a non-null predecessor must exist;
- BEFORE INSERT trigger: a non-null predecessor must have the same alias_id as
  NEW.alias_id and have no existing successor;
- BEFORE INSERT transition trigger: roots are CONFIRMED only; REASSIGNED and
  RETRACTED follow a targeted decision; RESTORED follows only RETRACTED;
  repeated RETRACTED is rejected; RESTORED requires a target, user actor, and
  nonblank rationale; and target shape/state ownership must be valid; and
- application repository validation repeats these checks for typed errors.

The two chain unique constraints provide optimistic concurrency. Concurrent
initial confirmations for one alias allow exactly one root; concurrent
reassign/retract/restore attempts for one active decision allow exactly one
successor. The loser becomes a safe typed IdentityResolutionConflictError
after rollback and no loser audit row remains.

Compound and state form a deduplicated immutable identity catalogue. They can
survive alias retraction or batch rollback like raw artifacts/audit history.
Catalog structural lookup continues to find them and marks dormant reuse;
active-alias lookup hides superseded, retracted, and rolled-back evidence.

## Atomic services

IdentityService exposes one import-facing operation:

    confirm_claim(result: CanonicalizationResult | None,
                  claim, report, selection, actor)

The clock is injected once into the IdentityService constructor and is not a
method argument. confirm_claim rejects claim.import_batch_id=None before
opening its one UnitOfWork. Within that transaction it validates the immutable
report/selection/actor and authority matrix, performs only the catalog action
declared in the report, appends Alias and root IdentityResolution, and appends
one AuditEvent whose import_batch_id equals Alias.import_batch_id. EXACT_STATE,
NEW_STATE, and NEW_COMPOUND require result. ALIAS_ONLY/AMBIGUOUS may receive
None and bind only a report-listed pre-existing compound without materializing
anything. The audit new_value_json includes hashes, policy/runtime provenance,
warning codes, report kind, catalog action, dormant/reuse-after-race status,
selected target, actor, and rationale. Failure at any flush or audit step rolls
back compound, state, alias, resolution, and audit together.

The remaining mutation signatures are:

    reassign(alias_id, predecessor_id, selection, actor)
    retract(alias_id, predecessor_id, actor)
    restore(alias_id, predecessor_id, selection, actor)

They append only one valid successor decision plus one batch-correlated
AuditEvent. restore accepts only an active RETRACTED
predecessor and explicit eligible target/user rationale; it never edits or
deletes the retraction. They do not materialize structures, modify Alias, or
permit a fork. No separate structure-materialization API is allowed because it
would create an unaudited partial identity.

## Test and acceptance requirements

RED-GREEN-REFACTOR must cover:

- mapped or atom-renumbered equivalent SMILES producing identical state hash;
- stereo/protomer/tautomer separation, policy hash payload changes, exact salt
  preservation, formula/mass golden values, and no persisted mass rounding;
- one-organic salt acceptance; two-organic co-crystal/tie QC failure; no
  incomplete parent persistence; and TautomerEnumerator non-Completed status;
- nullable InChIKey with inchi_unavailable warning/audit; empty-key rejection;
  and supplied-key-versus-SMILES conflict;
- source-system/source-value pair validation and bounded external data;
- populated 0001 migration including policy/runtime columns, checks, triggers,
  partial indexes, direct SQL protection, and corrupt-row safe errors;
- SQL source checks, UNIQUE(import_batch_id, source_system, source_value), and
  concurrent duplicate-alias insertion with one safe loser;
- concurrent root confirmation and concurrent reassign/retract/restore, one
  winner/one typed conflict, one committed audit, and no fork;
- reversible RETRACTED -> RESTORED chain and repeated-retraction rejection;
- PersistentIdentityIndex deterministic catalog/active-alias queries after
  reopen, dormant structural reuse, and alias exclusion for superseded,
  retracted, and rolled-back evidence;
- an empty-project NEW_COMPOUND confirmation followed by EXACT_STATE reuse;
- every authority-matrix rejection, especially exact-state sibling/downgrade;
  and
- atomic confirm_claim failure before any flush, after state flush,
  and before audit flush, proving no partial row persists.

Phase 2 passes only with 80%+ global/new-module branch coverage, safe populated
Phase 1 migration, pure resolver, persistent read-only projection, no silent
merge, complete authority enforcement, full verification gate, and Terra xhigh
review with no unresolved Critical or Important finding.
