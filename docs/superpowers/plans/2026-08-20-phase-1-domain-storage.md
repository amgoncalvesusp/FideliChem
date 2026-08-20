# FideliChem Phase 1 Domain and Storage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` to implement this plan task by task.
> Every production behavior follows RED-GREEN-REFACTOR.

**Goal:** Deliver a versioned SQLite project store with immutable domain values,
transactional repositories, raw-artifact provenance, append-only audit history,
and reversible import-batch lifecycle.

**Architecture:** Frozen Pydantic domain models remain independent from private
SQLAlchemy ORM rows. Repositories consume caller-owned sessions, while a unit of
work owns transaction boundaries. Alembic migrations are packaged with the
application. SQLite triggers enforce append-only evidence and audit records.

**Tech stack:** Python 3.12, Pydantic 2.x, SQLAlchemy 2.x, SQLite, Alembic 1.x,
pytest, Ruff, mypy, pip-audit, uv.

**Spec:** `docs/superpowers/specs/2026-08-20-phase-1-domain-storage-design.md`

## Global constraints

- Implement only `Project`, `ImportBatch`, `SourceArtifact`, and `AuditEvent`.
- Do not add chemistry, adapters, targets, docking, scores, analytics, GUI
  project flows, or portable artifact copying.
- All public values are frozen and extra input fields are rejected.
- Generate opaque UUID4 IDs in the application and persist them as text.
- Persist timezone-aware UTC timestamps without silently dropping offsets.
- Never physically delete project, batch, artifact, or audit rows.
- Never expose an update/delete repository operation for raw artifacts or audit.
- Apply `PRAGMA foreign_keys=ON` on every SQLite connection.
- Use one caller-owned transaction for each complete application operation.
- Add every schema change through Alembic; never call `metadata.create_all()` in
  production code.
- Use `UV_LINK_MODE=copy` for uv operations in this OneDrive workspace.
- Maintain at least 80% branch coverage globally and for new storage/domain code.

---

### Task 1: Locked dependencies and immutable domain primitives

**Files:**

- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Modify: `tests/checks/test_repository_configuration.py`
- Create: `src/fidelichem/domain/__init__.py`
- Create: `src/fidelichem/domain/errors.py`
- Create: `src/fidelichem/domain/ids.py`
- Create: `src/fidelichem/domain/json.py`
- Create: `src/fidelichem/domain/models.py`
- Create: `src/fidelichem/provenance/__init__.py`
- Create: `src/fidelichem/provenance/hashing.py`
- Create: `tests/unit/domain/test_models.py`
- Create: `tests/unit/domain/test_serialization.py`
- Create: `tests/unit/provenance/test_hashing.py`

**Produces:** frozen `Project`, `ImportBatch`, `SourceArtifact`, `AuditEvent`,
`ImportStatus`, typed domain errors, UUID factory, canonical JSON, SHA-256 bytes
and file helpers.

- [ ] Change the repository-configuration expectation first so it requires
  Pydantic, SQLAlchemy, and Alembic runtime dependencies; run that focused test
  and observe RED.
- [ ] Write model tests for frozen values, forbidden extra fields, non-blank
  names, UTC timestamps, valid status, non-negative counts/sizes, lowercase
  64-character SHA-256, safe relative paths, and preservation of null/zero.
- [ ] Write serialization/hash tests using known SHA-256 vectors, changed bytes,
  canonical key ordering, non-finite-number rejection, file streaming, and
  deterministic IDs tested as opaque UUID values. Run and observe RED imports.
- [ ] Add constrained runtime dependencies and regenerate the lockfile.
- [ ] Implement the smallest frozen models and utilities that turn the focused
  tests GREEN. Keep functions below 50 lines and avoid mutable defaults.
- [ ] Run focused coverage, Ruff, mypy, lock check, audit, build, pip check, full
  suite, and `git diff --check`; commit `feat: add immutable storage domain`.

---

### Task 2: SQLite engine and packaged initial migration

**Files:**

- Create: `src/fidelichem/storage/__init__.py`
- Create: `src/fidelichem/storage/engine.py`
- Create: `src/fidelichem/storage/orm.py`
- Create: `src/fidelichem/storage/migrations/__init__.py`
- Create: `src/fidelichem/storage/migrations/env.py`
- Create: `src/fidelichem/storage/migrations/versions/__init__.py`
- Create: `src/fidelichem/storage/migrations/versions/0001_initial_storage.py`
- Create: `src/fidelichem/storage/migrations/runner.py`
- Create: `tests/integration/storage/conftest.py`
- Create: `tests/integration/storage/test_engine.py`
- Create: `tests/integration/storage/test_migrations.py`

**Consumes:** domain models and errors from Task 1.

**Produces:** `create_sqlite_engine(path, read_only=False)`, ORM row mappings,
`upgrade_database(engine)`, `current_revision(engine)`, `head_revision()`, and
`assert_database_current(engine)`.

- [ ] Write tests proving every new/reopened connection has foreign keys on,
  paths resolve explicitly, read-only mode rejects writes, and invalid parents
  raise an integrity error. Run and observe RED.
- [ ] Write migration tests for a blank file to head, exact expected tables,
  indexes/constraints/triggers, repeat upgrade, reopen, current/head revision,
  future/unknown revision refusal, a one-row database guard for `project`, an
  `audit_event.import_batch_id` foreign key, `integrity_check`, and
  `foreign_key_check`. Prove direct SQL rejects a second project and an orphaned
  audit/batch correlation. Run and observe RED.
- [ ] Implement the SQLAlchemy 2 typed declarative base and four private row
  mappings with named constraints. No public caller may receive an ORM row.
- [ ] Implement the SQLite engine connection hook and packaged Alembic runner.
  Pass one existing connection to Alembic during programmatic upgrades.
- [ ] Implement revision `0001` with the four tables and triggers that reject
  artifact/audit update/delete and immutable-field changes on import batches.
- [ ] Turn the focused tests GREEN and verify that production never calls
  `metadata.create_all()`.
- [ ] Run the complete task gate and commit
  `feat: add versioned SQLite storage schema`.

---

### Task 3: Transactional repositories and unit of work

**Files:**

- Create: `src/fidelichem/storage/session.py`
- Create: `src/fidelichem/storage/repositories.py`
- Create: `tests/integration/storage/test_repositories.py`
- Create: `tests/integration/storage/test_transactions.py`

**Consumes:** immutable domain models and the migrated engine.

**Produces:** `UnitOfWork`, `ProjectRepository`, `ImportBatchRepository`,
`SourceArtifactRepository`, and `AuditRepository`.

- [ ] Write create/read/reopen tests for every Phase 1 entity, stable IDs and
  timestamps, empty/optional values, and exact hash/JSON round trips. Observe
  RED.
- [ ] Write tests proving missing records return `None`, duplicate IDs and
  relative paths fail, a second project with a distinct UUID fails, foreign-key
  violations fail, uncommitted data is hidden from a second connection, and an
  intermediate failure rolls back all writes.
- [ ] Implement session factory and context-managed unit of work. It commits only
  on successful exit and rolls back on any exception.
- [ ] Implement focused repositories that translate rows to fresh frozen domain
  values and use `flush()` without committing.
- [ ] Turn focused tests GREEN; refactor duplicated mapping without introducing a
  generic repository abstraction that obscures entity rules.
- [ ] Run the complete task gate and commit
  `feat: add transactional storage repositories`.

---

### Task 4: Immutable provenance, audited lifecycle, and rollback

**Files:**

- Modify: `src/fidelichem/storage/repositories.py`
- Create: `src/fidelichem/storage/services.py`
- Create: `tests/integration/storage/test_immutability.py`
- Create: `tests/integration/storage/test_import_lifecycle.py`
- Create: `tests/integration/storage/test_audit.py`

**Consumes:** Task 3 repositories and unit of work.

**Produces:** `StorageService.create_import_batch`,
`StorageService.complete_import_batch`, `StorageService.fail_import_batch`, and
`StorageService.rollback_import_batch` with atomic audit events.

- [ ] Write direct-SQL tests that `UPDATE`, `DELETE`, and `INSERT OR REPLACE`
  cannot change/remove artifacts or audit events, and that immutable batch
  fields cannot change. Observe RED where enforcement is incomplete.
- [ ] Write lifecycle tests for every legal/illegal transition, timestamp
  behavior, idempotent rollback, exactly one rollback event, and preservation of
  all artifacts and hashes.
- [ ] Write audit-order tests proving committed rows have strictly increasing
  sequences after reopen, failed transactions leave no observable audit row,
  gaps are permitted rather than contractually required, and callers never use
  the sequence as a domain identity.
- [ ] Write atomicity tests using a failpoint/callback: failure before audit or
  lifecycle flush leaves neither the state change nor a false success event.
- [ ] Implement lifecycle repository methods with optimistic expected-status
  predicates and typed transition errors.
- [ ] Implement the storage service so lifecycle mutation and audit append share
  one unit of work. A repeated rollback returns the unchanged batch and does not
  append another event.
- [ ] Turn focused tests GREEN, run SQLite integrity/FK checks, then run the
  complete task gate and commit
  `feat: add audited import batch lifecycle`.

---

### Task 5: Safe project layout and Phase 1 integration gate

**Files:**

- Create: `src/fidelichem/projects/__init__.py`
- Create: `src/fidelichem/projects/layout.py`
- Create: `src/fidelichem/projects/service.py`
- Create: `tests/integration/projects/test_project_service.py`
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `docs/implementation-status.md`

**Consumes:** migration runner, unit of work, and project repository.

**Produces:** immutable `ProjectPaths`, `create_project(root, name,
description=None)`, and `open_project(root, read_only=False)`.

- [ ] Write tests for the exact directory layout, canonical UTF-8
  `project.json`, migrated database, same-ID reopen, read-only reopen, Unicode,
  conflict refusal, unsafe manifest paths, and bounded cleanup after injected
  failure. Observe RED.
- [ ] Implement layout validation and project creation/opening. Never overwrite
  an existing database or manifest; never resolve a manifest path outside its
  project root.
- [ ] Add an end-to-end test that creates a project, opens a batch, records an
  artifact, completes and rolls it back, closes/reopens the project, and proves
  the immutable provenance and audit history remain intact.
- [ ] Update README and changelog only with behavior demonstrated by tests.
- [ ] Run the full Phase 1 gate with branch coverage and an additional coverage
  report scoped to `fidelichem.domain`, `fidelichem.provenance`,
  `fidelichem.storage`, and `fidelichem.projects`.
- [ ] Update `docs/implementation-status.md` with exact commit, commands/results,
  residual risks, and the next action; commit
  `feat: create persistent FideliChem projects`.

---

## Per-task verification gate

Run before every implementation commit:

```powershell
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
```

## Phase gate and handoff

After Tasks 1–5 have clean independent reviews:

1. Run the complete verification gate again from a clean controller state.
2. Inspect `git status`, commit history, and the full Phase 1 diff.
3. Dispatch a read-only Terra xhigh reviewer for specification compliance,
   correctness, security, migrations, atomicity, provenance, and missing tests.
4. Route every critical or important finding through an implementation worker
   and a fresh re-review; do not waive findings silently.
5. When clean, mark Phase 1 complete in `docs/implementation-status.md`, record
   the exact next action for Phase 2, and continue to Phase 2 under the user's
   standing instruction.
