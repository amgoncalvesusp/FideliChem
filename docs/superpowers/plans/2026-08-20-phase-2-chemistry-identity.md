# FideliChem Phase 2 Chemistry and Identity Resolver Implementation Plan

> **Execution gate:** This plan is queued. Execute it only after the Phase 1
> Terra gate is GO and its checkpoint says Phase 2 is active.
>
> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development to implement this plan task by task.
> Every production behavior follows RED-GREEN-REFACTOR.

**Goal:** Add a deterministic, provenance-safe chemistry identity core that
separates compound families from exact molecular states and never silently
merges aliases.

**Architecture:** RDKit is isolated behind a chemistry service returning fresh
frozen values. Private SQLAlchemy rows persist a deduplicated identity
catalogue and append-only source aliases/resolution decisions. The resolver is
pure and returns reports; a separate service persists explicit, audited
decisions under one unit of work.

**Tech stack:** Python 3.12, RDKit 2026.3.x, Pydantic 2.x, SQLAlchemy 2.x,
SQLite, Alembic 1.x, pytest, Hypothesis, Ruff, mypy, pip-audit, uv.

**Spec:** docs/superpowers/specs/2026-08-20-phase-2-chemistry-identity-design.md

## Global constraints

- Start only after the Phase 1 Terra gate is GO; preserve every Phase 1 public
  contract and migration behavior.
- Add runtime rdkit>=2026.3.4,<2026.4; the lockfile selects the exact version.
  Add Hypothesis only to the development dependency group.
- Only src/fidelichem/chemistry/** may import rdkit.
- All public values remain frozen Pydantic models with extra="forbid", UUID4
  IDs, UTC timestamps, non-finite-value rejection, and safe typed errors.
- Exact state preserves all sanitized components, stereo, charge, and tautomer
  supplied by the caller. It must not select a largest fragment or mutate raw
  source SMILES.
- Derive compound family only through the versioned pipeline FragmentParent ->
  ChargeParent -> TautomerParent -> RemoveStereochemistry.
- Hash inputs include fidelichem.molecular-state.v1 or
  fidelichem.compound-parent.v1.
- An InChIKey-only or alias-only claim is candidate evidence, never an
  unconditional automatic merge.
- The resolver has no SQLAlchemy import, repository access, mutation, audit,
  network, shell, GUI, or adapter dependency.
- Aliases and resolutions are append-only. Reassignment/retraction is a new
  superseding decision plus audit event, never update/delete.
- Do not add adapters, Import Manager, poses, targets, scores, analytics, GUI,
  fingerprints, enumeration, or scientific executable invocation.
- Use UV_LINK_MODE=copy for uv commands in this OneDrive workspace.
- Maintain at least 80% global and new-module branch coverage.

## File structure

| File or directory | Responsibility |
| --- | --- |
| src/fidelichem/domain/chemistry.py | Frozen chemistry and identity models. |
| src/fidelichem/domain/errors.py | Typed chemistry/identity public errors. |
| src/fidelichem/chemistry/policy.py | Limits, policy identifiers, and hash payloads. |
| src/fidelichem/chemistry/service.py | The only RDKit parser/canonicalizer. |
| src/fidelichem/storage/orm.py | Private Phase 2 identity row mappings. |
| src/fidelichem/storage/migrations/versions/0002_chemistry_identity.py | Safe expansion from Phase 1 schema. |
| src/fidelichem/storage/chemistry_repositories.py | Session-bound identity persistence. |
| src/fidelichem/identity/models.py | Claims, candidates, reports, and read-only index protocol. |
| src/fidelichem/identity/resolver.py | Pure deterministic matching. |
| src/fidelichem/identity/service.py | Audited materialization and reversible decisions. |
| docs/decisions/0002-compound-vs-state.md | Compound/state ADR. |
| docs/decisions/0005-identity-resolution.md | Resolution/override ADR. |

Tasks are serial because public contracts flow from domain to chemistry,
storage, resolver, and service. Use one fresh Luna xhigh writer per task; a
Terra xhigh reviewer must return GO before the next writer starts. Read-only
exploration and test design may run in parallel before Task 1, but concurrent
writers must not edit these shared files.

---

### Task 1: Lock dependencies and define frozen chemistry identity values

**Files:**

- Modify: pyproject.toml
- Modify: uv.lock
- Modify: tests/checks/test_repository_configuration.py
- Modify: src/fidelichem/domain/errors.py
- Modify: src/fidelichem/domain/__init__.py
- Create: src/fidelichem/domain/chemistry.py
- Create: tests/unit/domain/test_chemistry_models.py

**Consumes:** Phase 1 DomainModel, opaque IDs, SHA-256 type, UTC type,
ActorKind, canonical JSON, and UUID utilities.

**Produces:** Compound, MolecularState, Alias, IdentityResolution,
IdentityDecision, InchiKey, SourceSystem, and typed chemistry/identity errors.
This task does not import RDKit.

- [ ] **Step 1: Write failing configuration and model tests.**

  Require runtime rdkit>=2026.3.4,<2026.4 and development hypothesis>=6.0 in
  the repository-configuration test. Test frozen assignment, forbidden extras,
  canonical UUID4 IDs, aware UTC timestamps, SHA-256, pH 0/14 boundaries,
  finite positive mass, and preservation of None. Add failures for blank
  values, malformed InChIKeys, invalid source-system slugs, NUL/overlong
  aliases, and invalid decision target/supersession combinations.

      def test_retracted_resolution_has_no_target_and_supersedes_a_decision() -> None:
          resolution = IdentityResolution(
              alias_id=ALIAS_ID,
              decision=IdentityDecision.RETRACTED,
              compound_id=None,
              molecular_state_id=None,
              supersedes_id=PREVIOUS_ID,
              decided_at=NOW,
              actor_kind=ActorKind.USER,
          )
          assert resolution.compound_id is None

          with pytest.raises(ValueError):
              IdentityResolution(
                  alias_id=ALIAS_ID,
                  decision=IdentityDecision.RETRACTED,
                  compound_id=None,
                  molecular_state_id=None,
                  supersedes_id=None,
                  decided_at=NOW,
                  actor_kind=ActorKind.USER,
              )

- [ ] **Step 2: Run focused tests and observe RED.**

      $env:UV_LINK_MODE='copy'
      uv run pytest tests/checks/test_repository_configuration.py tests/unit/domain/test_chemistry_models.py -v

  Expected: absent domain chemistry module and dependency expectation failure.

- [ ] **Step 3: Add dependencies and implement the minimal values.**

  Regenerate the lockfile. Implement models and validators in the new domain
  module. Enforce this exact decision table:

      confirmed: compound_id is not None and supersedes_id is None
      reassigned: compound_id is not None and supersedes_id is not None
      retracted: compound_id is None and molecular_state_id is None
                 and supersedes_id is not None

  Export public values/errors from domain.__init__. Do not modify Phase 1 model
  fields or add persistence behavior.

- [ ] **Step 4: Run focused tests and verify GREEN.**

      uv run pytest tests/checks/test_repository_configuration.py tests/unit/domain/test_chemistry_models.py -v
      uv run ruff check src/fidelichem/domain tests/unit/domain tests/checks
      uv run mypy src/fidelichem/domain

- [ ] **Step 5: Run the task gate, inspect the diff, and commit.**

      git add pyproject.toml uv.lock tests/checks/test_repository_configuration.py src/fidelichem/domain tests/unit/domain/test_chemistry_models.py
      git commit -m "feat: add immutable chemistry identity models"

**Review gate:** Terra reviews domain validation, decision-state invariants,
scientific terminology, public error safety, and test completeness. Critical or
Important findings require a fresh Luna fix and a fresh Terra re-review.

---

### Task 2: Implement isolated RDKit canonicalization and versioned hashes

**Files:**

- Create: src/fidelichem/chemistry/__init__.py
- Create: src/fidelichem/chemistry/policy.py
- Create: src/fidelichem/chemistry/service.py
- Create: tests/unit/chemistry/test_service.py
- Create: tests/checks/test_rdkit_boundary.py

**Consumes:** Task 1 public models/errors and Phase 1 SHA-256 helpers.

**Produces:** ChemistryService.canonicalize(source_smiles, *, created_at) ->
CanonicalizationResult. It has no storage or resolver dependency.

- [ ] **Step 1: Write failing chemistry and boundary tests.**

  Test that CCO and OCC yield equal exact state hashes; valid stereoisomers,
  charged/neutral variants, and tautomeric variants yield distinct state hashes;
  and a multicomponent input retains a dot in state_smiles. Verify both policy
  strings affect hashes and parent isomeric SMILES is calculated only after
  stereo removal.

      def test_state_keeps_mixture_while_parentization_is_separate(service) -> None:
          result = service.canonicalize("CCO.[Cl-]", created_at=NOW)
          assert "." in result.molecular_state.state_smiles
          assert result.compound.structure_hash != result.molecular_state.state_hash

  Add parametrized RED cases for blank/NUL/10,001-character input, invalid
  syntax, more than 2,000 atoms, and unavailable/empty InChIKey. Assert typed
  errors omit untrusted input. Add an AST test rejecting rdkit imports outside
  the chemistry package.

- [ ] **Step 2: Run focused tests and observe RED.**

      $env:UV_LINK_MODE='copy'
      uv run pytest tests/unit/chemistry/test_service.py tests/checks/test_rdkit_boundary.py -v

  Expected: absent chemistry package and boundary failure.

- [ ] **Step 3: Implement the bounded chemistry service.**

  Put limits and pure hash payload helpers in policy.py. Validate before RDKit
  parsing, sanitize the exact molecule, calculate exact state values, and then
  use a copy for this fixed parent derivation:

      parent = FragmentParent(Chem.Mol(exact))
      parent = ChargeParent(parent)
      parent = TautomerParent(parent)
      Chem.RemoveStereochemistry(parent)

  Map parser/sanitization/InChI failures to safe typed errors. Return original
  validated input unchanged as CanonicalizationResult.source_smiles. Generate
  deterministic display/QC descriptors but permit equality only by state hash
  and compound parent hash.

- [ ] **Step 4: Run focused tests and verify GREEN.**

      uv run pytest tests/unit/chemistry/test_service.py tests/checks/test_rdkit_boundary.py -v
      uv run ruff check src/fidelichem/chemistry tests/unit/chemistry tests/checks/test_rdkit_boundary.py
      uv run mypy src/fidelichem/chemistry

- [ ] **Step 5: Run the task gate, inspect the diff, and commit.**

  Confirm all production RDKit imports are under fidelichem.chemistry and no
  public error includes raw molecular input.

      git add src/fidelichem/chemistry tests/unit/chemistry tests/checks/test_rdkit_boundary.py
      git commit -m "feat: add isolated RDKit canonicalization"

**Review gate:** Terra reviews exact/parent science, salt/mixture preservation,
API isolation, resource bounds, InChI failure behavior, and regression
coverage.

---

### Task 3: Add the append-only Phase 2 identity schema

**Files:**

- Modify: src/fidelichem/storage/orm.py
- Create: src/fidelichem/storage/migrations/versions/0002_chemistry_identity.py
- Modify: tests/integration/storage/test_migrations.py
- Create: tests/integration/storage/test_identity_migrations.py

**Consumes:** Task 1 models and the complete Phase 1 migration runner/schema.

**Produces:** private ORM rows and a safe populated-0001 to
0002_chemistry_identity upgrade. No repository API yet.

- [ ] **Step 1: Write failing real-SQLite migration tests.**

  Create a database at revision 0001_initial_storage, insert a project, batch,
  artifact, and audit row using only Phase 1 schema, then upgrade to head.
  Assert every old row survives and compound, molecular_state, alias, and
  identity_resolution have indexes, FKs, checks, and append-only triggers.

  Add direct-SQL tests that reject duplicate parent/state hashes, orphan rows,
  duplicate (batch, system, value) aliases, invalid decision shapes, a state
  assigned to another compound, update/delete/replace attempts, and forked
  supersedes_id. Retain repeated-upgrade/reopen/read-only/integrity/FK/Alembic
  metadata-drift tests.

- [ ] **Step 2: Run focused tests and observe RED.**

      $env:UV_LINK_MODE='copy'
      uv run pytest tests/integration/storage/test_migrations.py tests/integration/storage/test_identity_migrations.py -v

  Expected: 0002 and new table assertions fail.

- [ ] **Step 3: Implement private rows and migration 0002.**

  Add only underscored SQLAlchemy rows with UUID text, UtcTimestamp, named
  constraints/indexes, and no public ORM exposure. The migration creates the
  four tables in dependency order. identity_resolution has a unique nullable
  supersedes_id; confirmed has target/no predecessor, reassigned has both,
  retracted has predecessor/no target. Use a fixed SQL trigger to validate
  selected state ownership by compound and triggers rejecting updates/deletes
  on all four tables. Never interpolate application values into migration SQL.
  Write downgrade in reverse dependency order.

- [ ] **Step 4: Run focused tests and verify GREEN.**

      uv run pytest tests/integration/storage/test_migrations.py tests/integration/storage/test_identity_migrations.py -v

  Also run the existing storage migration suite, including its
  alembic.command.check test.

- [ ] **Step 5: Run the task gate, inspect the diff, and commit.**

  Update the expected table list for the new head while retaining all Phase 1
  object assertions.

      git add src/fidelichem/storage/orm.py src/fidelichem/storage/migrations/versions/0002_chemistry_identity.py tests/integration/storage/test_migrations.py tests/integration/storage/test_identity_migrations.py
      git commit -m "feat: add append-only chemistry identity schema"

**Review gate:** Terra reviews populated-Phase-1 compatibility, SQLite
triggers, append-only/reversibility semantics, FK restrictions, and error
surfaces.

---

### Task 4: Add transaction-bound identity catalogue repositories

**Files:**

- Create: src/fidelichem/storage/chemistry_repositories.py
- Modify: src/fidelichem/storage/session.py
- Modify: src/fidelichem/storage/__init__.py
- Create: tests/integration/storage/test_chemistry_repositories.py
- Create: tests/integration/storage/test_identity_transactions.py

**Consumes:** Task 1 models and Task 3 private rows/migration.

**Produces:** CompoundRepository, MolecularStateRepository, AliasRepository,
IdentityResolutionRepository, and active-only UoW properties compounds,
molecular_states, aliases, and identity_resolutions.

- [ ] **Step 1: Write failing repository and transaction tests.**

  Cover create/read/reopen of all Phase 2 values, unique hashes, missing reads,
  list-by-parent, list-by-alias, deterministic source/value/ID order, and
  resolution chains in decision-time order. A corrupt stored row must raise the
  Phase 1 safe CorruptStoredDataError.

  Test state-to-compound mismatch, missing source batch, deactivated
  repositories, caught flush failures that fail-close the UoW, and a failpoint
  proving a compound/state/alias/resolution group cannot commit partially.

- [ ] **Step 2: Run focused tests and observe RED.**

      $env:UV_LINK_MODE='copy'
      uv run pytest tests/integration/storage/test_chemistry_repositories.py tests/integration/storage/test_identity_transactions.py -v

  Expected: imports and UoW properties are absent.

- [ ] **Step 3: Implement focused repositories.**

  Reuse the Phase 1 repository lifecycle base rather than making generic CRUD.
  Each add() maps a frozen value to an underscored row, calls safe flush, and
  never commits. Each mapper catches malformed stored values and raises
  CorruptStoredDataError without SQL. Validate state ownership before flush and
  retain the trigger as an integrity backstop.

  Extend UnitOfWork._install_repositories() once and add all four repositories
  to its deactivation tuple. Preserve all Phase 1 repository and caller-owned
  session behavior.

- [ ] **Step 4: Run focused tests and verify GREEN.**

      uv run pytest tests/integration/storage/test_chemistry_repositories.py tests/integration/storage/test_identity_transactions.py -v
      uv run pytest tests/integration/storage -v

- [ ] **Step 5: Run the task gate, inspect the diff, and commit.**

      git add src/fidelichem/storage/chemistry_repositories.py src/fidelichem/storage/session.py src/fidelichem/storage/__init__.py tests/integration/storage/test_chemistry_repositories.py tests/integration/storage/test_identity_transactions.py
      git commit -m "feat: add transactional identity repositories"

**Review gate:** Terra reviews atomicity, lifecycle safety, direct-SQL
backstops, immutable mapping, ordering determinism, and rollback semantics.

---

### Task 5: Implement the pure identity resolver and ambiguity reports

**Files:**

- Create: src/fidelichem/identity/__init__.py
- Create: src/fidelichem/identity/models.py
- Create: src/fidelichem/identity/resolver.py
- Create: tests/unit/identity/test_resolution_models.py
- Create: tests/unit/identity/test_resolver.py

**Consumes:** Task 1 values and Task 2 ChemistryService protocol/result. It must
not consume storage repositories.

**Produces:** IdentityClaim, ResolutionCandidate, ResolutionReason,
ResolutionKind, ResolutionReport, IdentityIndex, and IdentityResolver.

- [ ] **Step 1: Write failing pure resolver tests using an immutable fake index.**

  The fake index returns prebuilt values by state hash, parent hash, full
  InChIKey, and source alias. Test same-SMILES/different-ID exact-state
  behavior; stereo/charged/tautomer state separation; new-state/one-parent
  behavior; missing SMILES; InChIKey-only one/many candidates; alias-only
  one/many candidates; retracted/superseded decisions excluded from alias
  lookup; deterministic order independent of insertion order; and
  structure/alias conflict.

      def test_structure_alias_conflict_never_selects_either_target(resolver, index) -> None:
          report = resolver.resolve(
              IdentityClaim(source_system="gold", source_value="ligand_7", smiles="CCO"),
              index,
          )
          assert report.kind is ResolutionKind.CONFLICT
          assert report.candidates == tuple(sorted(report.candidates, key=candidate_key))

  Add a static test that source under identity/resolver.py imports neither
  sqlalchemy nor fidelichem.storage and exposes no add/save/commit/write/delete
  public method.

- [ ] **Step 2: Run focused tests and observe RED.**

      $env:UV_LINK_MODE='copy'
      uv run pytest tests/unit/identity/test_resolution_models.py tests/unit/identity/test_resolver.py -v

  Expected: missing identity package/API.

- [ ] **Step 3: Implement immutable reports and pure matching.**

  Implement the read-only IdentityIndex protocol and resolver order exactly:
  canonicalize non-null SMILES; use only a unique exact state hash for
  EXACT_STATE; use a unique parent hash for NEW_STATE_FOR_COMPOUND; aggregate
  weaker evidence; detect disagreement before outcome; and return reasons
  instead of an opaque confidence score.

  Do not call repositories, mutate index-owned data, emit audit, or allow an
  external InChIKey to auto-merge.

- [ ] **Step 4: Run focused tests and verify GREEN.**

      uv run pytest tests/unit/identity/test_resolution_models.py tests/unit/identity/test_resolver.py -v
      uv run pytest tests/unit/chemistry/test_service.py tests/checks/test_rdkit_boundary.py -v

- [ ] **Step 5: Run the task gate, inspect the diff, and commit.**

      git add src/fidelichem/identity tests/unit/identity
      git commit -m "feat: add pure molecular identity resolver"

**Review gate:** Terra reviews evidence precedence, ambiguity/conflict behavior,
external-InChIKey policy, determinism, and scientifically misleading merge
risks.

---

### Task 6: Add explicit audited confirmation, reassignment, and retraction

**Files:**

- Create: src/fidelichem/identity/service.py
- Create: tests/integration/identity/test_identity_service.py
- Create: tests/integration/identity/test_identity_audit.py

**Consumes:** Task 4 UoW repositories, Task 5 reports, and Phase 1 AuditEvent.

**Produces:** IdentityService.materialize_structure, .confirm, .reassign, and
.retract. These are the only Phase 2 APIs that write resolutions.

- [ ] **Step 1: Write failing service and audit tests.**

  Test materializing a canonical result deduplicates parent/state hashes
  without creating an alias. Test confirm creates an Alias, initial confirmed
  resolution, and exactly one audit event under one UoW. A weak
  ALIAS_ONLY/AMBIGUOUS report requires a caller-supplied target; a CONFLICT
  report requires an explicit target and nonblank rationale.

  Test reassign creates a row superseding the active decision, retraction
  creates a no-target row, and only the newest unretracted chain member is
  active. Reject forks, repeated retraction, incompatible state/compound
  targets, and invented actor identity. Failpoints before resolution flush and
  audit flush must leave no alias/resolution/audit side effect.

- [ ] **Step 2: Run focused tests and observe RED.**

      $env:UV_LINK_MODE='copy'
      uv run pytest tests/integration/identity/test_identity_service.py tests/integration/identity/test_identity_audit.py -v

  Expected: IdentityService import failure.

- [ ] **Step 3: Implement the one-transaction service.**

  Inject a UoW factory and clock; callers never provide an ORM session.
  materialize_structure opens one UoW, reuses existing parent/state hashes, and
  appends only missing catalogue values. confirm validates report and target,
  appends Alias plus IdentityResolution(CONFIRMED) and one AuditEvent with
  canonical old/new JSON. It is allowed to auto-confirm only EXACT_STATE
  evidence; every weaker report requires an explicit target.

  reassign/retract query the active chain, validate that only its current row
  is superseded, append a new decision and one audit row, and never update or
  delete. Keep actor/source/rationale explicit; the service must not invent a
  user identity.

- [ ] **Step 4: Run focused tests and verify GREEN.**

      uv run pytest tests/integration/identity/test_identity_service.py tests/integration/identity/test_identity_audit.py -v
      uv run pytest tests/unit/identity tests/unit/chemistry tests/integration/storage -v

- [ ] **Step 5: Run the task gate, inspect the diff, and commit.**

  Confirm every successful resolution decision appends exactly one AuditEvent
  inside the same UoW.

      git add src/fidelichem/identity/service.py tests/integration/identity
      git commit -m "feat: add audited reversible identity decisions"

**Review gate:** Terra reviews confirmation authority, audit atomicity,
supersession/retraction correctness, error paths, and no-silent-merge behavior.

---

### Task 7: Record ADRs, phase evidence, and final integration gate

**Files:**

- Create: docs/decisions/0002-compound-vs-state.md
- Create: docs/decisions/0005-identity-resolution.md
- Modify: README.md
- Modify: CHANGELOG.md
- Modify: docs/implementation-status.md
- Create: tests/integration/identity/test_phase2_workflow.py

**Consumes:** all completed Phase 2 APIs and the completed Phase 1 project
service.

**Produces:** demonstrated-policy documentation, a project-level regression,
and the durable checkpoint for Phase 3.

- [ ] **Step 1: Write a failing end-to-end identity workflow.**

  Create/reopen a real project, canonicalize an exact multicomponent state,
  persist a confirmed source alias through IdentityService, resolve identical
  SMILES with another source ID to EXACT_STATE, then send a conflicting alias
  plus valid structure and assert it causes no mutation. Reassign and retract
  the initial decision, reopen, and assert aliases, resolution history, audit
  events, hashes, and active projection are reproducible.

- [ ] **Step 2: Run the workflow and observe RED.**

      $env:UV_LINK_MODE='copy'
      uv run pytest tests/integration/identity/test_phase2_workflow.py -v

  Expected: it fails until all earlier contracts compose through a project
  reopen.

- [ ] **Step 3: Make only integration fixes justified by the regression.**

  Do not add adapter behavior. Repair the smallest owner module and add a
  focused regression test beside any newly exposed branch.

- [ ] **Step 4: Document demonstrated behavior and verify GREEN.**

  ADR 0002 records state/parent pipeline, mixtures/salts, hash payloads, and
  non-goals. ADR 0005 records resolver evidence order, InChIKey restriction,
  ambiguity behavior, and append-only chains. Update README/changelog only
  with tested behavior.

      uv run pytest tests/integration/identity/test_phase2_workflow.py -v
      uv run pytest -v

- [ ] **Step 5: Run the full phase gate, checkpoint, and commit.**

      uv run pytest --cov=fidelichem.chemistry --cov=fidelichem.identity --cov=fidelichem.domain --cov=fidelichem.storage --cov-branch --cov-report=term-missing --cov-fail-under=80

  Inspect git status, complete Phase 2 diff, migration history, and SQLite
  integrity_check/foreign_key_check. Update implementation-status.md with exact
  commits, commands/results, RDKit lock version, residual risks, and next
  action: Phase 3 exploration.

      git add docs/decisions README.md CHANGELOG.md docs/implementation-status.md tests/integration/identity/test_phase2_workflow.py
      git commit -m "docs: complete phase two chemistry identity"

**Phase review gate:** Dispatch a fresh read-only Terra xhigh reviewer after the
full gate. Review specification compliance, state/parent science,
multi-component preservation, hash rules, migrations, provenance, InChIKey
behavior, alias conflicts, audit reversibility, security, and missing tests.
Fix every Critical/Important finding through a fresh Luna worker and re-run both
the relevant task review and this phase review. Only then mark Phase 2 complete
and begin Phase 3.

## Global verification gate

Run before every implementation commit and again at Phase 2 completion:

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
