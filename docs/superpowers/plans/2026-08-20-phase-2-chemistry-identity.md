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
read-only index implements the resolver protocol; the resolver itself remains
pure. One service transaction materializes a result, confirms its binding, and
writes a batch-correlated audit event atomically.

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
  reader is storage-side, read-only, deterministic, and filters superseded,
  retracted, and rolled-back evidence.
- Root/successor uniqueness, same-alias predecessor checks, state ownership,
  and append-only behavior are database constraints/triggers as well as
  repository validation.
- Only exact-state evidence may bind automatically. See Task 6 authority
  matrix; reject a sibling state or compound-only downgrade for exact evidence.
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
SourceSystem, CanonicalizationResult, IdentityClaim, and safe typed errors.
This task has no RDKit import.

- [ ] **Step 1: Write failing dependency and public-model tests.**

  Require the exact runtime dependency rdkit==2026.3.4 and development
  hypothesis>=6.0. Test frozen/extra/UUID/UTC/SHA/pH/finite-mass behavior.
  Require chemistry_policy_id and rdkit_version to be nonblank, permit
  inchi_version and both InChIKey fields to be None, and reject empty
  InChIKeys.

  Test source_system/source_value as both-or-neither on IdentityClaim, using
  the same lower-case slug, NUL, blank, and 1,024-character rules as Alias.
  Test confirmed/reassigned/retracted target truth tables and warning enum
  values. Test that source_smiles remains a supplied string rather than being
  synthesized from a state.

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

  Define typed errors including InvalidStructureError,
  TautomerEnumerationLimitError, AmbiguousParentStructureError,
  InchiUnavailableWarningCode handling, and IdentityResolutionConflictError.
  Export public values/errors without changing a Phase 1 model field.

- [ ] **Step 4: Run focused tests and verify GREEN.**

      uv run pytest tests/checks/test_repository_configuration.py tests/unit/domain/test_chemistry_models.py -v
      uv run ruff check src/fidelichem/domain tests/unit/domain tests/checks
      uv run mypy src/fidelichem/domain

- [ ] **Step 5: Run the task gate, inspect the diff, and commit.**

      git add pyproject.toml uv.lock tests/checks/test_repository_configuration.py src/fidelichem/domain tests/unit/domain/test_chemistry_models.py
      git commit -m "feat: add versioned chemistry identity models"

**Review gate:** Terra reviews optional-InChI semantics, durable provenance
fields, source-pair validation, target truth tables, typed diagnostics, and
public-model compatibility.

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
  Assert the partial unique root index permits roots for different aliases but
  rejects a second root for one alias. Assert unique supersedes_id rejects two
  successors. Assert the self-FK rejects an absent predecessor and a trigger
  rejects a successor whose predecessor belongs to a different alias or is
  already retracted.

  Create two direct-SQL writers that attempt root insertion for one alias and
  two that attempt successor insertion for one active row. The test may retry a
  SQLite locked writer after the winner commits; exactly one transaction must
  commit, the losing database operation must fail, and the stored chain must
  have no duplicate root or fork. Typed error mapping and atomic audit behavior
  are tested after their repository and service dependencies exist in Tasks 4
  and 7. Retain repeated-upgrade, read-only, reopen, integrity_check,
  foreign_key_check, and Alembic metadata-drift checks.

- [ ] **Step 2: Run focused tests and observe RED.**

      $env:UV_LINK_MODE='copy'
      uv run pytest tests/integration/storage/test_migrations.py tests/integration/storage/test_identity_migrations.py -v

  Expected: absent revision, columns, partial index, and trigger assertions.

- [ ] **Step 3: Implement private rows and fixed migration SQL.**

  Add underscored ORM rows only. The migration creates compound,
  molecular_state, alias, then identity_resolution. Add named FKs with
  RESTRICT, named checks, and indexes for hash/projection queries.

  Use:

      CREATE UNIQUE INDEX uq_identity_resolution_alias_root
      ON identity_resolution(alias_id)
      WHERE supersedes_id IS NULL;

  Add a self-FK on supersedes_id and a normal unique constraint on that column.
  A BEFORE INSERT trigger verifies predecessor same-alias/non-retracted state,
  valid decision shape, and state ownership by selected compound. Add
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
provenance fields, SQLite partial-index semantics, same-alias trigger rules,
concurrent writers, and append-only constraints.

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

  Test repository validation maps second-root, second-successor, and
  cross-alias predecessor failures to IdentityResolutionConflictError rather
  than raw SQL. Test two service-like caller-owned sessions attempting the
  same root/successor result in one winner and one typed conflict after retry.
  Test UoW deactivation/fail-closed semantics and atomic rollback after a
  second flush fails.

- [ ] **Step 2: Run focused tests and observe RED.**

      $env:UV_LINK_MODE='copy'
      uv run pytest tests/integration/storage/test_chemistry_repositories.py tests/integration/storage/test_identity_transactions.py -v

  Expected: repository/UoW imports are absent.

- [ ] **Step 3: Implement focused repositories.**

  Reuse the Phase 1 lifecycle base, safe flush path, and fresh frozen mapping.
  Repositories add/flush but never commit. Map constraints/trigger errors for
  root/successor/cross-alias races to IdentityResolutionConflictError; map
  locking after retry to the same safe public conflict where the state has
  changed. Preserve other Phase 1 integrity errors.

  Extend UnitOfWork._install_repositories once and include all new repositories
  in the same deactivation tuple. Do not alter Phase 1 repository semantics.

- [ ] **Step 4: Run focused tests and verify GREEN.**

      uv run pytest tests/integration/storage/test_chemistry_repositories.py tests/integration/storage/test_identity_transactions.py -v
      uv run pytest tests/integration/storage -v

- [ ] **Step 5: Run the task gate, inspect the diff, and commit.**

      git add src/fidelichem/storage/chemistry_repositories.py src/fidelichem/storage/session.py src/fidelichem/storage/__init__.py tests/integration/storage/test_chemistry_repositories.py tests/integration/storage/test_identity_transactions.py
      git commit -m "feat: add transactional identity repositories"

**Review gate:** Terra reviews error mapping, session ownership, race handling,
immutable mapping, and no partial transactions.

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
database queries.

- [ ] **Step 1: Write failing model and reopened-projection tests.**

  Define ResolutionKind, ResolutionReason, ResolutionCandidate, ResolutionReport,
  and IdentityIndex. Test frozen values and candidate sort key:
  compound ID, molecular-state ID with null last, then resolution ID.

  In a real project database, append roots, reassignment, retraction, aliases
  from completed batches, and aliases from a logically rolled-back batch. Close
  and reopen. Assert every persistent lookup by state hash, parent hash, full
  InChIKey, and alias returns deterministic tuples only through an active
  resolution and excludes superseded roots, retracted decisions, and
  rolled-back-batch evidence.

      def test_projection_hides_withdrawn_evidence_after_reopen(project) -> None:
          index = PersistentIdentityIndex(project.session_factory)
          assert index.by_alias("gold", "ligand_17") == ()
          assert index.by_state_hash(active_state.state_hash) == (active_candidate,)

  Add a static test that PersistentIdentityIndex performs only SQLAlchemy
  SELECT statements and that identity/models imports neither storage nor
  SQLAlchemy.

- [ ] **Step 2: Run focused tests and observe RED.**

      $env:UV_LINK_MODE='copy'
      uv run pytest tests/unit/identity/test_resolution_models.py tests/integration/storage/test_persistent_identity_index.py -v

  Expected: identity values and persistent reader are absent.

- [ ] **Step 3: Implement immutable values and SELECT-only projection.**

  Put protocol/report values in identity/models.py. Implement
  PersistentIdentityIndex in storage/identity_index.py with a factory for
  read-only sessions. Every lookup, including state hash, parent hash, and
  InChIKey, must join the same active-resolution projection: NOT EXISTS for a
  successor, decision != retracted, import_batch.status != rolled_back, and
  non-null compound target. Explicitly ORDER BY compound ID, state ID, and
  resolution ID in every candidate query.

  The class exposes no write method and does not import IdentityResolver. It
  maps rows to fresh immutable candidates and converts corrupted stored values
  to the existing safe storage error.

- [ ] **Step 4: Run focused tests and verify GREEN.**

      uv run pytest tests/unit/identity/test_resolution_models.py tests/integration/storage/test_persistent_identity_index.py -v
      uv run pytest tests/integration/storage -v

- [ ] **Step 5: Run the task gate, inspect the diff, and commit.**

      git add src/fidelichem/identity/__init__.py src/fidelichem/identity/models.py src/fidelichem/storage/identity_index.py tests/unit/identity/test_resolution_models.py tests/integration/storage/test_persistent_identity_index.py
      git commit -m "feat: add persistent identity projection"

**Review gate:** Terra reviews active-chain SQL, batch rollback filtering,
reopen behavior, ordering, read-only guarantee, and protocol boundaries.

---

### Task 6: Implement pure resolver with explicit authority matrix

**Files:**

- Create: src/fidelichem/identity/resolver.py
- Create: tests/unit/identity/test_resolver.py
- Create: tests/integration/identity/test_resolver_projection.py

**Consumes:** Tasks 2 and 5.

**Produces:** IdentityResolver.resolve(claim, index) -> ResolutionReport. The
persistent integration test passes PersistentIdentityIndex to the same pure
resolver API.

- [ ] **Step 1: Write failing resolver tests.**

  With a fake immutable index, test identical SMILES/different source IDs ->
  EXACT_STATE; a new exact state under one parent -> NEW_STATE_FOR_COMPOUND;
  stereo/charge/tautomer state separation; missing SMILES; alias-only and
  ambiguous aliases; external InChIKey-only candidates; deterministic order;
  and no weakened evidence auto-merge.

  Test supplied SMILES with a different non-null external InChIKey ->
  CONFLICT. Test structural evidence and active alias evidence to different
  targets -> CONFLICT. Repeat resolver cases using the reopened persistent
  index so an alias hidden by supersession/retraction/rollback cannot create a
  false conflict.

  Add a static source test: resolver.py imports neither SQLAlchemy nor storage
  and its public class has no add/save/commit/write/delete method.

- [ ] **Step 2: Run focused tests and observe RED.**

      $env:UV_LINK_MODE='copy'
      uv run pytest tests/unit/identity/test_resolver.py tests/integration/identity/test_resolver_projection.py -v

  Expected: IdentityResolver is absent.

- [ ] **Step 3: Implement pure evidence precedence.**

  Canonicalize valid SMILES first. If claim.inchikey and generated non-null
  state key differ, return CONFLICT. A unique state hash is EXACT_STATE; one
  parent hash without exact state is NEW_STATE_FOR_COMPOUND. Aggregate only
  active persistent alias/InChI candidates, detect disagreement before an
  outcome, and return reasons rather than a confidence score.

  The resolver only reports permitted targets. The service, not resolver,
  enforces the binding authority matrix. Do not mutate index-owned values or
  emit audit data.

- [ ] **Step 4: Run focused tests and verify GREEN.**

      uv run pytest tests/unit/identity/test_resolver.py tests/integration/identity/test_resolver_projection.py -v
      uv run pytest tests/unit/chemistry/test_service.py tests/integration/storage/test_persistent_identity_index.py -v

- [ ] **Step 5: Run the task gate, inspect the diff, and commit.**

      git add src/fidelichem/identity/resolver.py tests/unit/identity/test_resolver.py tests/integration/identity/test_resolver_projection.py
      git commit -m "feat: add pure identity resolution"

**Review gate:** Terra reviews conflict precedence, InChI evidence, persistent
projection use, deterministic results, and silent-merge resistance.

---

### Task 7: Implement one atomic materialize-plus-confirm and decision chain service

**Files:**

- Create: src/fidelichem/identity/service.py
- Create: tests/integration/identity/test_identity_service.py
- Create: tests/integration/identity/test_identity_audit.py
- Create: tests/integration/identity/test_identity_concurrency.py

**Consumes:** Tasks 2, 4, 5, and 6.

**Produces:** IdentityService.materialize_and_confirm, .reassign, and .retract.
There is no separate public materialize_structure followed by confirm operation.

- [ ] **Step 1: Write failing atomic, authority, and concurrency tests.**

  materialize_and_confirm must add missing compound/state, Alias, root
  IdentityResolution, and one AuditEvent in one UoW. Use injected failpoints
  before first chemistry flush, after state flush, after alias/resolution flush,
  and before audit flush; every failed call leaves all five categories absent.

  Assert audit_event.import_batch_id equals alias.import_batch_id and
  new_value_json contains policy ID, RDKit/InChI version, state/parent hash,
  report kind, warning codes, selected target, and override rationale.

  Test authority exactly:

  - EXACT_STATE only binds canonical exact state and its own compound; reject
    sibling state, other compound, or compound-only target.
  - NEW_STATE_FOR_COMPOUND materializes then binds the canonical exact state;
    reject a sibling/compound-only downgrade.
  - ALIAS_ONLY/AMBIGUOUS requires explicit user actor, compound target, and
    nonblank rationale; molecular_state_id must be null. Selecting a state
    requires a new structural claim and resolver report.
  - CONFLICT requires explicit override actor, target, and rationale.
  - UNRESOLVED cannot bind.

  Run two threads with a barrier attempting materialize_and_confirm for one
  alias and two threads reassigning one active resolution. Exactly one action
  succeeds in each race, one gets IdentityResolutionConflictError, one
  batch-correlated audit persists per successful action, and the chain has no
  fork.

- [ ] **Step 2: Run focused tests and observe RED.**

      $env:UV_LINK_MODE='copy'
      uv run pytest tests/integration/identity/test_identity_service.py tests/integration/identity/test_identity_audit.py tests/integration/identity/test_identity_concurrency.py -v

  Expected: IdentityService import failure.

- [ ] **Step 3: Implement one-UoW mutation and chain methods.**

  Inject a UoW factory, persistent index factory, clock, and bounded failpoint
  callback. materialize_and_confirm opens one UoW, reuses or appends the parent,
  reuses or appends the exact state, validates the report and authority matrix,
  appends Alias/root decision, and appends one AuditEvent. It must set the
  event import_batch_id from Alias, canonicalize audit JSON, and include
  inchi_unavailable warning when present. A typed chemistry parent/tautomer
  failure reaches this service before opening a write transaction.

  reassign/retract query the active row, append a same-alias successor, append
  one batch-correlated audit event, and never update Alias or a decision.
  Convert storage uniqueness/trigger conflict to
  IdentityResolutionConflictError after rollback. No public method may persist
  a compound/state without the simultaneous confirmation/audit flow.

- [ ] **Step 4: Run focused tests and verify GREEN.**

      uv run pytest tests/integration/identity/test_identity_service.py tests/integration/identity/test_identity_audit.py tests/integration/identity/test_identity_concurrency.py -v
      uv run pytest tests/unit/identity tests/unit/chemistry tests/integration/storage -v

- [ ] **Step 5: Run the task gate, inspect the diff, and commit.**

      git add src/fidelichem/identity/service.py tests/integration/identity/test_identity_service.py tests/integration/identity/test_identity_audit.py tests/integration/identity/test_identity_concurrency.py
      git commit -m "feat: add atomic audited identity confirmation"

**Review gate:** Terra reviews all-or-nothing behavior, batch audit correlation,
authority enforcement, warning audit, concurrent writers, and chain
reversibility.

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

  Create/reopen a real project. Confirm a map-bearing one-organic salt through
  materialize_and_confirm, reopen, construct PersistentIdentityIndex, and
  resolve an unmapped equivalent source ID to EXACT_STATE. Confirm that an
  InChI-unavailable result persists nullable key plus warning inside its audit.

  Attempt a two-organic co-crystal and non-Completed tautomer status; assert
  neither writes chemistry/alias/resolution/audit rows. Submit alias plus
  conflicting valid SMILES/InChI evidence; assert no mutation. Reassign then
  retract the initial decision, roll back its source batch through Phase 1
  StorageService, reopen, and assert PersistentIdentityIndex hides its alias
  evidence while raw alias/resolution/audit history remains queryable.

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
  non-goals. ADR 0005 states evidence precedence, persistent active projection,
  authority matrix, atomic audit, races, and reversible chain rules. Update
  README/changelog only with verified behavior.

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
persistent projection, authority matrix, atomic audit, security, and missing
tests. Fix every Critical/Important finding with a fresh Luna worker and repeat
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
