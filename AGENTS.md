# FideliChem Agent Instructions

Read `FideliChem_PLANO_CODEX.md` and the active phase specification before
editing. Work one phase at a time and stop after its review gate.

## Workflow

- Use a feature branch or isolated worktree; never implement on `main`.
- Use RED-GREEN-REFACTOR for production behavior and maintain at least 80%
  branch coverage.
- Delegate independent exploration, tests, and reviews. Never let concurrent
  writers edit the same files.
- Use Luna xhigh for bounded work, Terra xhigh for integration review, and Sol
  only for the escalation conditions in the product plan.
- Run the full suite, lint, type checking, dependency audit, and diff checks
  before every implementation commit and phase completion claim.

## Architecture and scientific safety

- Raw evidence is immutable; transformations must be traceable.
- Molecule, molecular state, pose, run, score definition, and observation are
  distinct concepts.
- Missing data is never silently converted to zero.
- Adapters return canonical bundles and never write to the database.
- GUI code contains no scientific rules or direct SQL.
- Validate all external data at boundaries and fail with clear errors.
- Never execute imported files, use pickle or `eval`, hardcode secrets, copy
  incompatible third-party code, or distribute proprietary executables.

Prefer small focused modules, explicit immutable values, parameterized data
access, and user-facing errors that do not expose sensitive details.
