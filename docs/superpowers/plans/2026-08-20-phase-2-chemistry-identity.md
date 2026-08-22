# FideliChem Phase 2 Chemistry and Identity Resolver Implementation Plan

> **Execution gate:** This plan is queued. Execute it only after the Phase 1
> Terra gate is GO and the durable checkpoint marks Phase 2 active.
>
> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development to implement this plan task by task.
> Every production behavior follows RED-GREEN-REFACTOR.

**Goal:** Add a deterministic, provenance-safe identity core that separates
compound families from exact molecular states, uses a persistent read-only
identity projection, and never silently merges a source alias.

**Architecture:** Frozen domain values are defined before chemistry code. RDKit
is isolated in one bounded service. Private ORM rows and append-only database
rules hold the identity catalogue and resolution chains. A storage-side
read-only index implements separate immutable-catalog and active-alias resolver
lookups; the resolver itself remains pure. One service transaction confirms a
claim, performs only its report-authorized catalog action, and writes a
batch-correlated audit event atomically.

**Tech stack:** Python 3.12, RDKit 2026.3.4, Pydantic 2.x, SQLAlchemy 2.x,
SQLite, Alembic 1.x, pytest, Hypothesis, Ruff, mypy, pip-audit, uv.

**Spec:** docs/superpowers/specs/2026-08-20-phase-2-chemistry-identity-design.md

## Global constraints

- Begin only after Phase 1 Terra GO. Preserve Phase 1 migration, project,
  lifecycle, provenance, audit, session, and error contracts.
- Add runtime rdkit==2026.3.4 exactly. Add hypothesis>=6.0 only to dev.
- Only src/fidelichem/chemistry may import rdkit.
- Every public value is frozen, extra="forbid", UUID4/UTC safe, and rejects
  non-finite numbers. No public error/log contains raw SMILES, SQL, or path.
- ChemistryPolicy v1 has the fixed parent pipeline FragmentParent ->
  ChargeParent -> ConfiguredTautomerParent -> RemoveStereochemistry,
  maxTautomers=128, and maxTransforms=256.
- Clear atom maps on an identity copy before every serialization/hash/InChI
  calculation. Preserve raw source_smiles separately for provenance.
- Exact state is never reduced to its parent. Two organic components never
  receive an automatic parent representative.
- Any chemistry-policy/transform/limit/hash change requires a new policy ID
  and new hash prefixes. Persist policy ID, RDKit version, and nullable InChI
  version on durable Compound and MolecularState rows.
- InChIKey is nullable evidence, never an empty string. An unavailable key
  creates a QC warning carried into the atomic audit event.
- The pure resolver never imports storage/SQLAlchemy or writes. The persistent
  reader is storage-side, read-only, deterministic, queries all immutable
  catalog rows for structural evidence, and filters superseded, retracted, and
  rolled-back evidence only from active-alias lookup.
- NEW_COMPOUND is the explicit no-match structural outcome. It creates the
  compound and exact state atomically; it is never inferred inside the service.
- Root/successor uniqueness, same-alias predecessor checks, state ownership,
  and append-only behavior are database constraints/triggers as well as
  repository validation.
- Alias has UNIQUE(import_batch_id, source_system, source_value) plus matching
  SQL source-field checks. RETRACTED is reversible only by an explicit
  RESTORED successor; repeated retraction is invalid.
- Only exact-state evidence may bind automatically. See Task 6 authority
  matrix; reject a sibling state or compound-only downgrade for exact evidence.
- IdentityService receives its clock only in the constructor. confirm_claim
  rejects a null import batch and accepts CanonicalizationResult | None under
  the report authority matrix.
- No adapters, Import Manager, GUI, target, pose, score, MD, ML, fingerprint,
  broad tautomer enumeration, shell, network, pickle, eval, or scientific
  executable belongs in this phase.
- Use UV_LINK_MODE=copy in this OneDrive workspace. Maintain at least 80%
  global and new-module branch coverage.

## File structure and serial ownership

| Area | Exact files |
| --- | --- |
| Frozen chemistry values | domain/chemistry.py, domain/errors.py, domain/__init__.py |
| RDKit boundary | chemistry/__init__.py, chemistry/policy.py, chemistry/service.py |
| Schema | storage/orm.py, migrations/versions/0002_chemistry_identity.py |
| Persistence | storage/chemistry_repositories.py, storage/session.py, storage/__init__.py |
| Read-only projection | storage/identity_index.py |
| Resolver | identity/__init__.py, identity/models.py, identity/resolver.py |
| Atomic write service | identity/service.py |
| ADR and phase evidence | decisions/0002-compound-vs-state.md, decisions/0005-identity-resolution.md |

All writer tasks are serial. Each task has a fresh Luna xhigh writer and a
read-only Terra xhigh review before its successor begins. Luna explorers may
map RDKit APIs, SQLite partial-index behavior, and resolution test matrices in
parallel before Task 1; their outputs do not change files.

---

### Task 1: Pin RDKit and define immutable, provenance-bearing domain values

**Files:**

- Modify: pyproject.toml
- Modify: uv.lock
- Modify: tests/checks/test_repository_configuration.py
- Modify: src/fidelichem/domain/errors.py
- Modify: src/fidelichem/domain/__init__.py
- Create: src/fidelichem/domain/chemistry.py
- Create: tests/unit/domain/test_chemistry_models.py

**Consumes:** Phase 1 DomainModel, OpaqueId, Sha256Digest, UtcTimestamp,
ActorKind, UUID helpers, and JSON rules.

**Produces:** Compound, MolecularState, Alias, IdentityResolution,
IdentityDecision, ChemistryWarning, ChemistryWarningCode, InchiKey,
SourceSystem, CanonicalizationResult, IdentityClaim, IdentitySelection,
SelectionMode, IdentityActor, and safe typed errors. This task has no RDKit
import.

- [ ] **Step 1: Write failing dependency and public-model tests.**

  Require the exact runtime dependency rdkit==2026.3.4 and development
  hypothesis>=6.0. Test frozen/extra/UUID/UTC/SHA/pH/finite-mass behavior.
  Require chemistry_policy_id and rdkit_version to be nonblank, permit
  inchi_version and both InChIKey fields to be None, and reject empty
  InChIKeys.

  Test source_system/source_value as both-or-neither on IdentityClaim, using
  the same lower-case slug, NUL, blank, and 1,024-character rules as Alias.
  Test confirmed/reassigned/retracted/restored target/predecessor shapes.
  Database/service transition tests in Tasks 3 and 7 prove RESTORED follows
  only RETRACTED and repeated retraction is invalid. Test SelectionMode
  existing_target/new_compound shapes and frozen
  actor rules: user needs bounded nonblank actor_id; system has null actor_id;
  rationale is null-or-bounded-nonblank. Test warning enum values and that
  source_smiles remains supplied rather than synthesized from a state.

      def test_claim_rejects_one_half_of_source_alias() -> None:
          with pytest.raises(ValueError, match="together"):
              IdentityClaim(
                  source_system="gold",
                  source_value=None,
                  smiles=None,
                  inchikey=None,
                  import_batch_id=None,
              )

      def test_inchi_is_nullable_but_never_empty() -> None:
          state = valid_state.model_copy(update={"state_inchikey": None})
          assert state.state_inchikey is None
          with pytest.raises(ValueError):
              MolecularState.model_validate(
                  {**valid_state.model_dump(), "state_inchikey": ""}
              )

- [ ] **Step 2: Run focused tests and observe RED.**

      $env:UV_LINK_MODE='copy'
      uv run pytest tests/checks/test_repository_configuration.py tests/unit/domain/test_chemistry_models.py -v

  Expected: dependency assertion and absent chemistry-domain imports fail.

- [ ] **Step 3: Add dependencies and implement domain validation.**

  Regenerate the lockfile. Implement fields exactly as the specification. Use
  model validation rather than Pydantic model_copy assumptions for the decision
  rules:

      confirmed  -> compound_id present, supersedes_id absent
      reassigned -> compound_id present, supersedes_id present
      retracted  -> compound_id/state_id absent, supersedes_id present
      restored   -> compound_id present, supersedes_id present,
                    user actor, nonblank rationale

  Define typed errors including InvalidStructureError,
  TautomerEnumerationLimitError, AmbiguousParentStructureError,
  InchiUnavailableWarningCode handling, AliasConflictError, and
  IdentityResolutionConflictError.
  Export public values/errors without changing a Phase 1 model field.

- [ ] **Step 4: Run focused tests and verify GREEN.**

      uv run pytest tests/checks/test_repository_configuration.py tests/unit/domain/test_chemistry_models.py -v
      uv run ruff check src/fidelichem/domain tests/unit/domain tests/checks
      uv run mypy src/fidelichem/domain

- [ ] **Step 5: Run the task gate, inspect the diff, and commit.**

      git add pyproject.toml uv.lock tests/checks/test_repository_configuration.py src/fidelichem/domain tests/unit/domain/test_chemistry_models.py
      git commit -m "feat: add versioned chemistry identity models"

**Review gate:** Terra reviews optional-InChI semantics, durable provenance
fields, source-pair validation, selection/actor contracts, restoration truth
tables, typed diagnostics, and public-model compatibility.

---

### Task 2: Implement bounded RDKit canonicalization with versioned policy

**Files:**

- Create: src/fidelichem/chemistry/__init__.py
- Create: src/fidelichem/chemistry/policy.py
- Create: src/fidelichem/chemistry/service.py
- Create: tests/unit/chemistry/test_policy.py
- Create: tests/unit/chemistry/test_service.py
- Create: tests/checks/test_rdkit_boundary.py

**Consumes:** Task 1 values/errors and Phase 1 SHA-256 helpers.

**Produces:** explicit ChemistryPolicy and
ChemistryService.canonicalize(source_smiles, *, created_at) ->
CanonicalizationResult. No persistence/resolver dependency.

- [ ] **Step 1: Write failing policy and canonicalization tests.**

  Assert the only default policy is fidelichem.rdkit-identity.v1 with hash
  prefixes and maxTautomers=128/maxTransforms=256. Assert a policy mutation
  changes neither an existing value nor its hash; instead the policy
  constructor rejects same-ID/different-algorithm configuration.

  Test CCO and OCC equality; atom-mapped and map-renumbered forms equal their
  unmapped state hash; stereo, charged, and tautomer variants differ in exact
  state hash; and every calculated serialization/hash plus Compound formula and
  mass ignores atom maps.
  Use fixed golden values for CCO.[Cl-]: exact state retains components while
  the supported one-organic parent has formula C2H6O and average molecular
  weight pytest.approx(46.069, abs=1e-12). Also assert the persisted value
  round-trips exactly from the service result, with no application rounding.

      def test_atom_maps_are_not_identity(service) -> None:
          unmapped = service.canonicalize("CCO", created_at=NOW)
          mapped = service.canonicalize("[CH3:7][CH2:2][OH:99]", created_at=NOW)
          assert mapped.molecular_state.state_hash == unmapped.molecular_state.state_hash
          assert mapped.source_smiles == "[CH3:7][CH2:2][OH:99]"

  Test one organic component plus a salt succeeds; two organic components such
  as CCO.CCO raises AmbiguousParentStructureError with code
  CHEMISTRY_PARENT_MULTIORGANIC; no-organic input raises the declared parent
  error; and neither result can be materialized later. Test blank/NUL/10,001
  characters/invalid syntax/2,001 atoms without exposing input in error text.

  Mock the configured enumerator's result status as non-Completed and assert
  TautomerEnumerationLimitError. Mock InChI unavailable/empty: it must yield
  None and warning code inchi_unavailable, never an empty key. Test the exact
  descriptor string prefixes and hash payload components. Test the AST rule
  forbidding RDKit imports outside chemistry.

- [ ] **Step 2: Run focused tests and observe RED.**

      $env:UV_LINK_MODE='copy'
      uv run pytest tests/unit/chemistry/test_policy.py tests/unit/chemistry/test_service.py tests/checks/test_rdkit_boundary.py -v

  Expected: chemistry package/API does not exist.

- [ ] **Step 3: Implement policy, safe diagnostics, and service.**

  policy.py defines the immutable v1 policy, its hash payload functions, and
  max limits. service.py validates size before parsing, disables/captures RDKit
  diagnostics locally, sanitizes, and copies the molecule. Clear every atom map
  number on that identity copy before every derived value.

  Count carbon-containing disconnected components on the exact identity copy.
  Accept exactly one organic component with inorganic salts/counterions; reject
  zero or more than one organic component before parent persistence. Verify
  FragmentParent derives its representative from that sole carbon-containing
  component and raise the typed parent-policy error if it does not. For an
  accepted parent, use FragmentParent then ChargeParent, run a fresh configured
  TautomerEnumerator through Enumerate, reject status other than Completed,
  select its canonical result, then remove stereochemistry.

  Use CalcMolFormula(parent) and Descriptors.MolWt(parent) without rounding.
  Store actual RDKit runtime version, nullable InChI library version, and policy
  ID in both durable model values. Generate an optional key; turn unavailable
  output into the declared warning. Return source_smiles unchanged. Do not
  serialize/map/hash raw source text and do not log it.

- [ ] **Step 4: Run focused tests and verify GREEN.**

      uv run pytest tests/unit/chemistry/test_policy.py tests/unit/chemistry/test_service.py tests/checks/test_rdkit_boundary.py -v
      uv run ruff check src/fidelichem/chemistry tests/unit/chemistry tests/checks/test_rdkit_boundary.py
      uv run mypy src/fidelichem/chemistry

- [ ] **Step 5: Run the task gate, inspect the diff, and commit.**

      git add src/fidelichem/chemistry tests/unit/chemistry tests/checks/test_rdkit_boundary.py
      git commit -m "feat: add bounded RDKit identity canonicalization"

**Review gate:** Terra reviews map stripping, policy versioning, enum status
handling, salt/co-crystal rules, exact formula/mass semantics, InChI fallback,
and diagnostic safety.

---

### Task 3: Create schema 0002 with durable chemistry provenance and chain rules

**Files:**

- Modify: src/fidelichem/storage/orm.py
- Create: src/fidelichem/storage/migrations/versions/0002_chemistry_identity.py
- Modify: tests/integration/storage/test_migrations.py
- Create: tests/integration/storage/test_identity_migrations.py

**Consumes:** Task 1 values and the completed Phase 1 migration runner/schema.

**Produces:** private rows and a real populated-0001 to
0002_chemistry_identity migration. No repository API yet.

- [ ] **Step 1: Write failing migration and direct-SQL tests.**

  Build a database at 0001_initial_storage, insert Phase 1 project/batch/
  artifact/audit rows, upgrade to head, and assert all old rows survive.
  Assert the four identity tables exist with policy ID, RDKit version, nullable
  InChI version, parent/state hashes, and all required named indexes/triggers.

  Direct SQL must reject duplicate parent/state hashes, orphaned state/alias/
  resolution rows, empty policy/runtime fields, invalid decision/target shape,
  state/compound mismatch, update/delete/replace, and an empty InChIKey.
  Assert UNIQUE(import_batch_id, source_system, source_value). Direct SQL must
  reject an uppercase/invalid/over-128 source_system and NUL, blank-only, or
  over-1,024 source_value while accepting the same source pair in a different
  batch.
  Assert the partial unique root index permits roots for different aliases but
  rejects a second root for one alias. Assert unique supersedes_id rejects two
  successors. Assert the self-FK rejects an absent predecessor and a trigger
  rejects a successor whose predecessor belongs to a different alias. Assert
  REASSIGNED/RETRACTED follow only a targeted active predecessor, RESTORED
  follows only RETRACTED with target/user/rationale, a repeated retraction is
  rejected, and a restored row may itself be retracted later.

  Create two direct-SQL writers for the same alias unique tuple, two that
  attempt root insertion for one alias, and two that attempt successor
  insertion for one active row. The test may retry a SQLite locked writer after
  the winner commits; exactly one transaction in each race must commit, the
  losing operation must fail, and stored state must contain no duplicate alias,
  duplicate root, or fork. Typed error mapping and atomic audit behavior are
  tested after their repository/service dependencies exist in Tasks 4 and 7.
  Retain repeated-upgrade, read-only, reopen, integrity_check,
  foreign_key_check, and Alembic metadata-drift checks.

- [ ] **Step 2: Run focused tests and observe RED.**

      $env:UV_LINK_MODE='copy'
      uv run pytest tests/integration/storage/test_migrations.py tests/integration/storage/test_identity_migrations.py -v

  Expected: absent revision, columns, partial index, and trigger assertions.

- [ ] **Step 3: Implement private rows and fixed migration SQL.**

  Add underscored ORM rows only. The migration creates compound,
  molecular_state, alias, then identity_resolution. Add named FKs with
  RESTRICT, uq_alias_batch_source over
  UNIQUE(import_batch_id, source_system, source_value), and
  ck_alias_source_system_format/ck_alias_source_value_bounds matching the
  domain slug, length, blank, and NUL rules. Add indexes for hash/projection
  queries.

  Use:

      CREATE UNIQUE INDEX uq_identity_resolution_alias_root
      ON identity_resolution(alias_id)
      WHERE supersedes_id IS NULL;

  Add a self-FK on supersedes_id and a normal unique constraint on that column.
  BEFORE INSERT triggers verify same-alias/no-successor predecessor state,
  valid CONFIRMED/REASSIGNED/RETRACTED/RESTORED transitions, repeated-retract
  rejection, RESTORED user/rationale requirements, and state ownership by the
  selected compound. Add
  no-update/no-delete triggers to all four identity tables. Implement downgrade
  in dependency reverse order. Do not interpolate application input into any
  migration SQL.

- [ ] **Step 4: Run focused tests and verify GREEN.**

      uv run pytest tests/integration/storage/test_migrations.py tests/integration/storage/test_identity_migrations.py -v

  Run the pre-existing storage migration suite and its Alembic command.check
  test.

- [ ] **Step 5: Run the task gate, inspect the diff, and commit.**

      git add src/fidelichem/storage/orm.py src/fidelichem/storage/migrations/versions/0002_chemistry_identity.py tests/integration/storage/test_migrations.py tests/integration/storage/test_identity_migrations.py
      git commit -m "feat: add concurrent-safe chemistry identity schema"

**Review gate:** Terra reviews populated-Phase-1 compatibility, schema
provenance fields, alias SQL checks/unique race, SQLite partial-index semantics,
restoration transition rules, concurrent writers, and append-only constraints.

---

### Task 4: Add transaction-bound identity repositories and conflict mapping

**Files:**

- Create: src/fidelichem/storage/chemistry_repositories.py
- Modify: src/fidelichem/storage/session.py
- Modify: src/fidelichem/storage/__init__.py
- Create: tests/integration/storage/test_chemistry_repositories.py
- Create: tests/integration/storage/test_identity_transactions.py

**Consumes:** Tasks 1 and 3.

**Produces:** CompoundRepository, MolecularStateRepository, AliasRepository,
IdentityResolutionRepository, active-only UoW properties, and typed mapping of
chain conflicts.

- [ ] **Step 1: Write failing repository/transaction tests.**

  Cover create/read/reopen, unique hashes, nullable InChI fields, exact
  policy/runtime round trips, missing reads, deterministic list ordering, and
  safe corrupt-row conversion. Verify state ownership and source-batch FKs.

  Test repository validation maps duplicate batch/source alias to
  AliasConflictError and second-root, second-successor, cross-alias predecessor,
  and invalid restore/retract transitions to IdentityResolutionConflictError
  rather than raw SQL. Test two
  service-like caller-owned sessions attempting the same alias/root/successor
  result in one winner and one typed conflict after retry. Test UoW
  deactivation/fail-closed semantics and atomic rollback after a second flush
  fails.

- [ ] **Step 2: Run focused tests and observe RED.**

      $env:UV_LINK_MODE='copy'
      uv run pytest tests/integration/storage/test_chemistry_repositories.py tests/integration/storage/test_identity_transactions.py -v

  Expected: repository/UoW imports are absent.

- [ ] **Step 3: Implement focused repositories.**

  Reuse the Phase 1 lifecycle base, safe flush path, and fresh frozen mapping.
  Repositories add/flush but never commit. Map constraints/trigger errors for
  alias races to AliasConflictError and root/successor/cross-alias/transition
  races to IdentityResolutionConflictError; map locking after retry to the
  corresponding safe public conflict where state has changed. Preserve other
  Phase 1 integrity errors.

  Extend UnitOfWork._install_repositories once and include all new repositories
  in the same deactivation tuple. Do not alter Phase 1 repository semantics.

- [ ] **Step 4: Run focused tests and verify GREEN.**

      uv run pytest tests/integration/storage/test_chemistry_repositories.py tests/integration/storage/test_identity_transactions.py -v
      uv run pytest tests/integration/storage -v

- [ ] **Step 5: Run the task gate, inspect the diff, and commit.**

      git add src/fidelichem/storage/chemistry_repositories.py src/fidelichem/storage/session.py src/fidelichem/storage/__init__.py tests/integration/storage/test_chemistry_repositories.py tests/integration/storage/test_identity_transactions.py
      git commit -m "feat: add transactional identity repositories"

**Review gate:** Terra reviews alias/chain error mapping, session ownership,
restore/retract races, immutable mapping, and no partial transactions.

---

### Task 5: Define resolver values and implement persistent read-only index

**Files:**

- Create: src/fidelichem/identity/__init__.py
- Create: src/fidelichem/identity/models.py
- Create: src/fidelichem/storage/identity_index.py
- Create: tests/unit/identity/test_resolution_models.py
- Create: tests/integration/storage/test_persistent_identity_index.py

**Consumes:** Tasks 1 and 4.

**Produces:** IdentityIndex protocol, resolution report values, and
PersistentIdentityIndex, which implements the protocol through SELECT-only
database queries over separate immutable-catalog and active-alias surfaces.

- [ ] **Step 1: Write failing model and reopened-projection tests.**

  Define ResolutionKind including NEW_STATE and NEW_COMPOUND, ResolutionReason,
  EvidenceKind, CatalogAction, ResolutionCandidate, ResolutionReport, and
  IdentityIndex. Test frozen values; immutable sorted evidence tuples;
  catalog_action/catalog_match_dormant invariants; and candidate sort key:
  compound ID, molecular-state ID with null last, then resolution ID null last.

  In a real project database, append roots, reassignment, retraction, aliases
  from completed batches, and aliases from a logically rolled-back batch. Close
  and reopen. Construct the index from project.engine and separately assert:

  - catalog_by_state_hash, catalog_by_parent_hash, and
    catalog_by_generated_inchikey return deterministic immutable catalog rows
    regardless of alias supersession/retraction/rollback;
  - active_by_alias excludes superseded roots, retracted decisions, and
    rolled-back-batch evidence; and
  - catalog candidates with no active alias are marked catalog_dormant=true.

      def test_projection_hides_withdrawn_evidence_after_reopen(project) -> None:
          index = PersistentIdentityIndex(project.engine)
          assert index.active_by_alias("gold", "ligand_17") == ()
          candidate = index.catalog_by_state_hash(dormant_state.state_hash)[0]
          assert candidate.catalog_dormant is True

  Add a static test that PersistentIdentityIndex performs only SQLAlchemy
  SELECT statements, accepts the existing Phase 1 Engine | SessionFactory
  contract, does not access an undeclared project-level session factory, and
  that identity/models imports neither storage nor SQLAlchemy.

- [ ] **Step 2: Run focused tests and observe RED.**

      $env:UV_LINK_MODE='copy'
      uv run pytest tests/unit/identity/test_resolution_models.py tests/integration/storage/test_persistent_identity_index.py -v

  Expected: identity values and persistent reader are absent.

- [ ] **Step 3: Implement immutable values and SELECT-only projection.**

  Put protocol/report values in identity/models.py. Implement
  PersistentIdentityIndex in storage/identity_index.py to accept Engine |
  SessionFactory and open owned read-only sessions. Catalog hash/generated-
  InChI methods query Compound/MolecularState directly across all rows and use
  an EXISTS subquery only to mark active versus dormant. active_by_alias alone
  uses the lifecycle projection: NOT EXISTS successor, decision != retracted,
  import_batch.status != rolled_back, and non-null compound target. Explicitly
  ORDER BY compound ID, state ID, and resolution ID null last in every query.

  The class exposes no write method and does not import IdentityResolver. It
  maps rows to fresh immutable candidates and converts corrupted stored values
  to the existing safe storage error.

- [ ] **Step 4: Run focused tests and verify GREEN.**

      uv run pytest tests/unit/identity/test_resolution_models.py tests/integration/storage/test_persistent_identity_index.py -v
      uv run pytest tests/integration/storage -v

- [ ] **Step 5: Run the task gate, inspect the diff, and commit.**

      git add src/fidelichem/identity/__init__.py src/fidelichem/identity/models.py src/fidelichem/storage/identity_index.py tests/unit/identity/test_resolution_models.py tests/integration/storage/test_persistent_identity_index.py
      git commit -m "feat: add persistent identity projection"

**Review gate:** Terra reviews catalog-versus-alias SQL separation, dormant
marking, batch rollback filtering, Engine/SessionFactory ownership, reopen
behavior, ordering, read-only guarantee, and protocol boundaries.

---

### Task 6: Implement pure resolver with explicit authority matrix

**Files:**

- Create: src/fidelichem/identity/resolver.py
- Create: tests/unit/identity/test_resolver.py
- Create: tests/integration/identity/test_resolver_projection.py

**Consumes:** Tasks 2 and 5.

**Produces:** IdentityResolver.resolve(result: CanonicalizationResult | None,
claim, index) -> ResolutionReport. The persistent integration test passes
PersistentIdentityIndex to the same pure resolver API.

- [ ] **Step 1: Write failing resolver tests.**

  With a fake immutable index, test an exact catalog state -> EXACT_STATE; a
  new exact state under one catalog parent -> NEW_STATE; valid canonical
  structure with no state/parent match and no conflict -> NEW_COMPOUND;
  stereo/charge/tautomer state separation; result None; alias-only and
  ambiguous aliases; external InChIKey-only candidates; deterministic order;
  and no weakened evidence auto-merge. An empty index plus valid result must
  return NEW_COMPOUND with catalog_action=create_compound.

  Test supplied SMILES with a different non-null external InChIKey ->
  CONFLICT. Test structural evidence and active alias evidence to different
  targets -> CONFLICT. Repeat resolver cases using the reopened persistent
  index: an alias hidden by supersession/retraction/rollback cannot create a
  false conflict, but an identical dormant state still returns EXACT_STATE with
  reuse_state/catalog_match_dormant=true. A dormant parent returns NEW_STATE
  with reuse_compound/catalog_match_dormant=true.

  Add a static source test: resolver.py imports neither SQLAlchemy nor storage
  and its public class has no add/save/commit/write/delete method.

- [ ] **Step 2: Run focused tests and observe RED.**

      $env:UV_LINK_MODE='copy'
      uv run pytest tests/unit/identity/test_resolver.py tests/integration/identity/test_resolver_projection.py -v

  Expected: IdentityResolver is absent.

- [ ] **Step 3: Implement pure evidence precedence.**

  Accept a precomputed result rather than importing RDKit. If claim.inchikey
  and generated non-null state key differ, return CONFLICT. A unique catalog
  state hash is EXACT_STATE; one catalog parent hash without exact state is
  NEW_STATE; zero structural matches with no conflict is NEW_COMPOUND. Query
  generated InChI across the catalog as candidate evidence only. Aggregate
  active alias evidence separately, detect disagreement before an outcome, and
  return reasons/catalog action/dormant markers rather than a confidence score.

  The resolver only reports permitted targets. The service, not resolver,
  enforces the binding authority matrix. Do not mutate index-owned values or
  emit audit data. result=None is valid only when claim.smiles is None; when
  both are present, result.source_smiles must equal claim.smiles exactly.

- [ ] **Step 4: Run focused tests and verify GREEN.**

      uv run pytest tests/unit/identity/test_resolver.py tests/integration/identity/test_resolver_projection.py -v
      uv run pytest tests/unit/chemistry/test_service.py tests/integration/storage/test_persistent_identity_index.py -v

- [ ] **Step 5: Run the task gate, inspect the diff, and commit.**

      git add src/fidelichem/identity/resolver.py tests/unit/identity/test_resolver.py tests/integration/identity/test_resolver_projection.py
      git commit -m "feat: add pure identity resolution"

**Review gate:** Terra reviews NEW_COMPOUND completeness, catalog/dormant versus
active-alias precedence, conflict/InChI evidence, deterministic results, and
silent-merge resistance.

---

### Task 7: Implement atomic claim confirmation and reversible decision chains

**Files:**

- Create: src/fidelichem/identity/service.py
- Create: tests/integration/identity/test_identity_service.py
- Create: tests/integration/identity/test_identity_audit.py
- Create: tests/integration/identity/test_identity_concurrency.py

**Consumes:** Tasks 2, 4, 5, and 6.

**Produces:** IdentityService.confirm_claim, .reassign, .retract, and .restore.
There is no separate public structure-materialization operation.

- [ ] **Step 1: Write failing atomic, authority, and concurrency tests.**

  Construct IdentityService with its clock, UoW/index factories, and bounded
  failpoint callback. Its exact mutation signature is:

      confirm_claim(result: CanonicalizationResult | None,
                    claim, report, selection, actor)

  A NEW_COMPOUND call must add Compound, exact state, Alias, root resolution,
  and one AuditEvent in one UoW. Use failpoints before first chemistry flush,
  after state flush, after alias/resolution flush, and before audit flush; every
  failed call leaves all five categories absent. Reject import_batch_id=None
  before UoW creation. Assert no mutation method accepts a clock parameter.

  Assert audit_event.import_batch_id equals alias.import_batch_id and
  new_value_json contains policy ID, RDKit/InChI version, state/parent hash,
  report kind, catalog action, dormant/reuse-after-race flag, warning codes,
  selected target, actor, and rationale.

  Test authority exactly:

  - EXACT_STATE requires result and reuses/binds only the report's exact state;
    reject sibling state, other compound, or compound-only target.
  - NEW_STATE requires result, reuses only the report's parent, materializes
    and binds the result exact state, and rejects sibling/compound-only target.
  - NEW_COMPOUND requires result and new_compound selection, creates/binds both
    structures, and rejects IDs or pre-existing arbitrary targets. If an
    identical uniqueness race wins first, reload only matching hashes and
    audit reuse_after_race without changing report kind.
  - ALIAS_ONLY/AMBIGUOUS may pass result=None; require user actor, report-listed
    pre-existing compound, null state, and nonblank rationale. If result is
    supplied, prove no Compound/MolecularState row is added from it.
  - CONFLICT requires user actor, a candidate listed in report, and rationale.
  - UNRESOLVED cannot bind.

  Reject a selection absent from report, mismatched catalog action, arbitrary
  compound, wrong sibling state, system override, missing/overlong actor ID or
  rationale, and a report/result hash mismatch. Prove catalog reuse and dormant
  reuse exactly match report fields and audit fields; never silently convert a
  NEW_COMPOUND report into NEW_STATE or EXACT_STATE.

  Prove retraction then RESTORED appends a target/user/rationale successor while
  keeping both old rows; repeated retract fails. Run barrier races for the same
  batch/source alias tuple and for two reassign/retract/restore successors of
  one active resolution. Exactly one action succeeds; the alias loser gets
  AliasConflictError and a chain loser gets IdentityResolutionConflictError.
  One batch-correlated audit persists for the winner, no losing audit remains,
  and the chain has no fork.

- [ ] **Step 2: Run focused tests and observe RED.**

      $env:UV_LINK_MODE='copy'
      uv run pytest tests/integration/identity/test_identity_service.py tests/integration/identity/test_identity_audit.py tests/integration/identity/test_identity_concurrency.py -v

  Expected: IdentityService import failure.

- [ ] **Step 3: Implement one-UoW mutation and chain methods.**

  Inject a UoW factory, persistent index factory, clock, and bounded failpoint
  callback only into the constructor. confirm_claim rejects a null batch,
  validates result/report/selection/actor, opens one UoW, and performs exactly
  report.catalog_action. It then appends Alias/root decision and one AuditEvent.
  Set event import_batch_id from Alias, canonicalize audit JSON, and include
  inchi_unavailable, catalog dormant/reuse, and actor information. ALIAS_ONLY/
  AMBIGUOUS never call catalog add methods. A typed chemistry parent/tautomer
  failure reaches this service before opening a write transaction.

  reassign/retract/restore query the active row, validate the transition and
  user actor/rationale, append a same-alias successor and one batch-correlated
  audit event, and never update Alias or an existing decision. restore accepts
  only RETRACTED and an eligible pre-existing target; retract accepts only a
  targeted active decision.
  Convert duplicate-alias conflict to AliasConflictError and chain
  uniqueness/trigger conflict to IdentityResolutionConflictError after
  rollback. No public method may persist a compound/state without simultaneous
  confirmation/audit flow.

- [ ] **Step 4: Run focused tests and verify GREEN.**

      uv run pytest tests/integration/identity/test_identity_service.py tests/integration/identity/test_identity_audit.py tests/integration/identity/test_identity_concurrency.py -v
      uv run pytest tests/unit/identity tests/unit/chemistry tests/integration/storage -v

- [ ] **Step 5: Run the task gate, inspect the diff, and commit.**

      git add src/fidelichem/identity/service.py tests/integration/identity/test_identity_service.py tests/integration/identity/test_identity_audit.py tests/integration/identity/test_identity_concurrency.py
      git commit -m "feat: add atomic audited identity confirmation"

**Review gate:** Terra reviews exact confirm_claim signature/constructor clock,
all-or-nothing behavior, batch/alias requirements, report-selection authority,
NEW_COMPOUND and dormant/race reuse audit, actor rules, concurrent writers, and
RETRACTED/RESTORED reversibility.

---

### Task 8: Record ADRs and close the Phase 2 integration gate

**Files:**

- Create: docs/decisions/0002-compound-vs-state.md
- Create: docs/decisions/0005-identity-resolution.md
- Modify: README.md
- Modify: CHANGELOG.md
- Modify: docs/implementation-status.md
- Create: tests/integration/identity/test_phase2_workflow.py

**Consumes:** all Phase 2 contracts and completed Phase 1 project service.

**Produces:** documented decisions, project/reopen regression, and exact
checkpoint for Phase 3 exploration.

- [ ] **Step 1: Write the failing project workflow regression.**

  Start with a truly empty real project and an active import batch. Canonicalize
  a map-bearing one-organic salt, resolve it against
  PersistentIdentityIndex(project.engine) to NEW_COMPOUND, select
  new_compound, and confirm_claim atomically. Assert Compound, exact state,
  alias, resolution, and audit all exist. Reopen the project and resolve an
  unmapped equivalent source ID to EXACT_STATE/catalog reuse. Confirm an
  InChI-unavailable result persists nullable key plus warning inside its audit.

  Create a new exact state of the same parent and prove NEW_STATE reuses the
  parent. Confirm an alias-only claim with result=None against a report-listed
  existing compound and prove no catalog row is added. Reject the same call
  with import_batch_id=None and reject an arbitrary existing target not in the
  report.

  Attempt a two-organic co-crystal and non-Completed tautomer status; assert
  neither writes chemistry/alias/resolution/audit rows. Submit alias plus
  conflicting valid SMILES/InChI evidence; assert no mutation. Reassign then
  retract the initial decision, prove repeated retract fails, RESTORE it with
  explicit target/user/rationale, then retract again. Reopen and assert active
  alias evidence is hidden while the same structural state still resolves
  EXACT_STATE with catalog_match_dormant=true. Roll back its source batch
  through Phase 1 StorageService, reopen, and assert the alias remains hidden,
  catalog reuse remains available, and raw alias/resolution/audit history is
  still queryable.

- [ ] **Step 2: Run the workflow and observe RED.**

      $env:UV_LINK_MODE='copy'
      uv run pytest tests/integration/identity/test_phase2_workflow.py -v

  Expected: failure until all contracts compose after a real database reopen.

- [ ] **Step 3: Make only integration fixes justified by the regression.**

  Do not add adapters or GUI. Place each fix in the smallest owner module and
  add a focused regression when the workflow exposes a branch not already
  covered by Tasks 1 through 7.

- [ ] **Step 4: Document demonstrated policy and verify GREEN.**

  ADR 0002 states exact versus parent semantics, map stripping, salt/co-crystal
  rule, enumerator limits/status, formula/mass units, policy evolution, and
  non-goals. ADR 0005 states NEW_COMPOUND/NEW_STATE/EXACT_STATE completeness,
  immutable-catalog versus active-alias lookup, dormant reuse, InChI evidence,
  IdentitySelection/IdentityActor authority, exact confirm_claim signature,
  constructor-only clock, alias uniqueness, atomic audit/races, and explicit
  RETRACTED -> RESTORED chain rules. Update README/changelog only with verified
  behavior.

      uv run pytest tests/integration/identity/test_phase2_workflow.py -v
      uv run pytest -v

- [ ] **Step 5: Run full phase gate, checkpoint, and commit.**

      uv run pytest --cov=fidelichem.chemistry --cov=fidelichem.identity --cov=fidelichem.domain --cov=fidelichem.storage --cov-branch --cov-report=term-missing --cov-fail-under=80

  Inspect migration history, git status, complete Phase 2 diff, and SQLite
  integrity_check/foreign_key_check. Record exact commits, commands/results,
  RDKit/InChI runtime provenance, risks, and Phase 3 exploration as next
  action in implementation-status.md.

      git add docs/decisions README.md CHANGELOG.md docs/implementation-status.md tests/integration/identity/test_phase2_workflow.py
      git commit -m "docs: complete phase two chemistry identity"

**Phase review gate:** Dispatch fresh Terra xhigh review after the full gate.
It must review spec compliance, map/hash science, policy versioning, salts/co-
crystals, tautomer completion, optional InChI, migration/concurrency rules,
  catalog/alias projections, NEW_COMPOUND empty-project flow, selection/actor
  authority, restore transitions, atomic audit, security, and missing tests.
  Fix every Critical/Important finding with a fresh Luna worker and repeat
the relevant task review plus full phase review. Mark Phase 2 complete only
after GO.

## Global verification gate

Run before every implementation commit and again at Phase completion:

    $env:UV_LINK_MODE='copy'
    $env:QT_QPA_PLATFORM='offscreen'
    uv lock --check
    uv run ruff check .
    uv run mypy src/fidelichem
    uv run pytest --cov=fidelichem --cov-branch --cov-report=term-missing --cov-fail-under=80
    uv run pip-audit
    uv build
    uv pip check
    git diff --check
