# Task 8 — Phase 2 integration gate report

- Status: **DONE_WITH_CONCERNS**
- Date: 2026-08-22
- Branch: `feat/fidelichem-mvp-phases-1-16`
- Scope: project/reopen workflow, ADRs, phase checkpoint, and verification

## RED

The first complete workflow was run before changing production code:

```powershell
$env:UV_LINK_MODE='copy'
uv run pytest tests/integration/identity/test_phase2_workflow.py -v
```

Result: **1 failed**. The workflow correctly produced a `CONFLICT` report for
an alias combined with conflicting valid SMILES/InChI evidence, but the test
initially attempted a report-listed human target and expected no write. The
failure demonstrated that the frozen contract permits a user override of a
conflict when the target is report-listed and rationale-bearing. No service
change was retained. The regression was corrected to submit the conflict to
the pure resolver and attempt an unauthorized sibling-state selection; that
selection is rejected before a unit of work and the database remains
unchanged. This preserves the valid human override contract.

## GREEN

Focused workflow after the test correction:

```text
uv run pytest tests/integration/identity/test_phase2_workflow.py -v
1 passed in 1.48s
```

Final phase coverage gate:

```powershell
$env:UV_LINK_MODE='copy'
$env:QT_QPA_PLATFORM='offscreen'
uv run pytest --cov=fidelichem.chemistry --cov=fidelichem.identity --cov=fidelichem.domain --cov=fidelichem.storage --cov-branch --cov-report=term-missing --cov-fail-under=80
```

Result: **454 passed in 46.20s; 90.40% branch coverage** (2083 statements,
490 branches, 75 partial branches; required threshold 80%). The identity
service was 82% in this scoped report. The final run covers the complete
suite, including the new workflow.

## Changes

- Added `tests/integration/identity/test_phase2_workflow.py` covering a real
  empty project, active batch, map-bearing one-organic salt, atomic
  `NEW_COMPOUND`, reopen and `EXACT_STATE`, parent-reusing `NEW_STATE`,
  nullable InChI warning audit, alias-only confirmation without catalog rows,
  resolver-only claims and pre-UoW persistence validation, report-bound
  selection, two-organic/co-crystal rejection, incomplete tautomer status,
  conflict evidence with unauthorized selection, reassign/retract/restore/
  retract, reopen projection, and Phase 1 batch rollback.
- Added ADR 0002 documenting Compound versus MolecularState, map stripping,
  conservative salt/co-crystal policy, tautomer limits/status, formula/mass
  units, policy evolution, and non-goals.
- Added ADR 0005 documenting resolution completeness, immutable catalog versus
  active aliases, dormant reuse, InChI evidence, actor/selection authority,
  report binding, report-free human mutation, the exact confirmation
  signature, constructor-only clock, persistence boundary, uniqueness,
  candidate-granular dormancy, atomic audit/races, and explicit resolution
  chain rules.
- Updated `README.md`, `CHANGELOG.md`, and `docs/implementation-status.md`
  only with behavior exercised by tests and existing frozen contracts.
- No adapter, GUI, migration, or production identity-service change was
  retained. The temporary broad conflict rejection was removed after applying
  the contract ruling that a rationale-bearing user may explicitly confirm a
  report-listed conflict target.

## Exact verification commands and results

```text
uv lock --check
Resolved 60 packages in 1ms

uv run ruff check .
All checks passed!

uv run mypy src/fidelichem
Success: no issues found in 40 source files

uv run pip-audit
No known vulnerabilities found
fidelichem: Dependency not found on PyPI and could not be audited: fidelichem (0.1.0)

uv build
Successfully built dist\fidelichem-0.1.0.tar.gz
Successfully built dist\fidelichem-0.1.0-py3-none-any.whl

uv pip check
Checked 60 packages in 4ms
All installed packages are compatible

git diff --check
passed (only Git LF/CRLF normalization warnings for README.md and CHANGELOG.md)
```

The final unscoped suite was also run with `uv run pytest -v`: **454 passed in
38.55s**. The final coverage invocation above is the authoritative post-change
full-suite result.

## Runtime provenance

```text
rdkit=2026.03.4
inchi=1.07.3
```

The service validates the RDKit runtime semantically as `(2026, 3, 4)` and the
lockfile pins `rdkit==2026.3.4`. The installed binding reports the equivalent
zero-padded display string `2026.03.4`.

## Migration and SQLite checks

Migration history was inspected with the packaged Alembic script:

```text
head= 0002_chemistry_identity
history=[('0002_chemistry_identity', '0001_initial_storage', 'Add immutable chemistry identity and resolution history tables.'), ('0001_initial_storage', None, 'Create the initial immutable Phase 1 storage schema.')]
```

On a fresh temporary migrated SQLite database:

```text
revision= 0002_chemistry_identity head= 0002_chemistry_identity integrity_check= ok foreign_key_check= []
```

## Commits

- Implementation commit: `b152505` — `docs: complete phase two chemistry
  identity`.
- This report is added in the follow-up documentation commit so the
  implementation hash is stable and directly verifiable.

## Remaining concerns and next action

The local gate is complete, but the required fresh Terra xhigh Phase 2 review
has not yet run in this worker. It must review map/hash science, policy
versioning, salts/co-crystals, tautomer completion, optional InChI,
migration/concurrency rules, catalog/alias projections, empty-project
`NEW_COMPOUND`, selection/actor authority, restore transitions, atomic audit,
security, and missing tests. Phase 2 must remain pending until that review is
GO. After GO, the exact next action is Phase 3 adapter-SDK exploration.
