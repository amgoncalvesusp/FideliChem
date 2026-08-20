# FideliChem Phase 0 Bootstrap Design

## Status and source of truth

This specification narrows Phase 0 of `FideliChem_PLANO_CODEX.md` into an
implementable bootstrap. The product plan remains the source of truth for all
later phases and scientific invariants. Phase 0 creates only the application
shell and its engineering guardrails.

## Goal

Create an installable, testable Python desktop project whose CLI reports its
version, whose Qt shell starts and exits cleanly, whose operational logging is
safe to configure more than once, and whose checks run on Windows and Ubuntu.

## Scope

Phase 0 includes:

- a Python package using the `src/` layout;
- package metadata and a reproducible `uv.lock`;
- console and GUI entry points;
- a minimal PySide6 main window with no scientific behavior;
- idempotent operational logging;
- unit, integration, subprocess smoke, and Qt tests;
- branch coverage enforcement at 80% or higher;
- CI on Windows and Ubuntu;
- Codex project configuration and specialized agent definitions;
- project-level contributor instructions and bootstrap documentation.

It explicitly excludes molecular domain models, RDKit, storage, migrations,
adapters, imports, provenance records, analytics, decision logic, and production
packaging artifacts. Those belong to later phases of the product plan.

## Chosen approach

Use a deliberately small bootstrap with Python 3.12, `uv` for environment and
lock management, and Hatchling as the PEP 517 build backend. PySide6 is the only
runtime dependency. Test and quality tools live in a development dependency
group; PyInstaller is deferred until the packaging phase rather than exercised
by the Phase 0 CI gate.

This approach is preferred over Python 3.11 because the current bootstrap
dependencies support 3.12 and the product plan explicitly permits it. It is
preferred over installing the entire future scientific stack because unused
dependencies would enlarge the compatibility and security surface without
satisfying any Phase 0 acceptance criterion. Compatibility with RDKit must be
rechecked before the chemistry phase rather than assumed here.

## Package and file boundaries

The bootstrap will keep production modules focused:

- `fidelichem.__init__` owns the public version constant.
- `fidelichem.__main__` delegates `python -m fidelichem` to the CLI.
- `fidelichem.cli` owns argument parsing and the `--version` contract.
- `fidelichem.app.logging` owns operational logging configuration.
- `fidelichem.gui.application` owns `QApplication` creation and event-loop
  startup.
- `fidelichem.gui.main_window` owns the domain-free main window.

No module in this phase may import or define scientific entities. Empty package
trees for future phases will not be created merely to mirror the final desired
layout; each package will appear when it gains a concrete responsibility.

## Public contracts

### Version and CLI

The package exposes a semantic version through `fidelichem.__version__`.
`fidelichem.cli:main` accepts an optional argument sequence and returns an
integer exit code. The installed `fidelichem` command and
`python -m fidelichem` both support:

- `--version`, which prints exactly one version line and exits with code 0;
- `--help`, which prints usage and exits with code 0;
- invalid arguments, which print a concise argparse error and exit with a
  non-zero code.

The CLI performs no database, chemistry, or adapter work in Phase 0.

### Qt shell

`fidelichem.gui.application:create_application(argv)` returns the existing
`QApplication` instance when one is present or creates one otherwise.
`fidelichem.gui.application:main(argv)` creates a `MainWindow`, shows it, and
runs the Qt event loop. The installed `fidelichem-gui` entry point calls this
function.

`MainWindow` presents only the FideliChem product name and a neutral empty-state
message. It contains no project, import, database, or scientific logic. Tests
must be able to create, show, and close it with `pytest-qt` without relying on
pixel comparisons or timing sleeps.

### Operational logging

`fidelichem.app.logging:configure_logging(level)` configures the `fidelichem`
logger namespace with a predictable human-readable console handler. Repeated
calls update the level without adding duplicate handlers. This is operational
application logging only; it is not the future scientific audit/provenance log.
Startup failures are logged without exposing environment secrets.

## Dependencies and tooling

- Python: exactly the 3.12 minor line, expressed as `>=3.12,<3.13`.
- Environment and lock: `uv` with committed `uv.lock` and `.python-version`.
- Build backend: Hatchling.
- Runtime: PySide6 6.x, constrained below 7.
- Development: pytest, pytest-qt, coverage with TOML support, Ruff, and mypy.
- Packaging: no PyInstaller configuration or binary artifact in Phase 0.

The future scientific dependencies named in the product plan are not declared
until the phase that first uses them.

## Test strategy

Implementation follows strict RED-GREEN-REFACTOR. Each behavioral production
contract receives a failing test before its implementation. Configuration-only
files are validated with explicit checks but do not substitute for behavioral
tests.

The Phase 0 suite covers:

- public version validity and consistency;
- CLI help, version, and invalid-argument behavior;
- installed/module CLI subprocess smoke behavior;
- idempotent logging configuration;
- one-application Qt factory behavior;
- creation, display, and clean closure of the main window;
- a bounded headless GUI startup smoke path that cannot hang indefinitely.

Coverage uses branch measurement and fails below 80%. Qt tests use
`QT_QPA_PLATFORM=offscreen`, `qtbot`, event-aware waits, explicit cleanup, and
no arbitrary sleeps. Tests do not share `QSettings`, clipboard, locale, or
filesystem state.

The long-term test directory reserves clear homes for unit, integration, GUI,
smoke, adapter fixtures, golden cases, and scientific regressions, but Phase 0
creates only directories containing real tests or documentation.

## Continuous integration

GitHub Actions runs the locked environment on `windows-latest` and
`ubuntu-latest`, both using Python 3.12. Each job:

1. checks out the repository;
2. installs `uv` using its maintained action;
3. synchronizes the locked development environment;
4. checks that the lockfile is current;
5. runs Ruff, mypy, and the complete pytest suite with branch coverage;
6. builds the Python distribution and verifies dependency consistency.

Ubuntu sets the Qt offscreen platform. The workflow contains no release,
publishing, signing, or binary packaging side effects.

## Codex and contributor configuration

`.codex/config.toml` enables the multi-agent workflow supported by the current
Codex configuration schema and caps concurrency at six. Agent definitions match
the roles and model routing from the product plan: Luna xhigh for bounded work,
Terra xhigh for integration review, and Sol only for explicit escalation.

The repository `AGENTS.md` records phase discipline, TDD, security, immutable
raw evidence, adapter/storage separation, and the requirement to stop at each
phase gate. It does not duplicate the full product plan.

## Error handling and security

- Bootstrap errors return non-zero CLI/process status and a concise user-facing
  message while retaining diagnostic context in operational logs.
- Imported files are never executed; Phase 0 introduces no import facility.
- No secrets, tokens, telemetry, network services, `eval`, pickle, or executable
  third-party scientific software are introduced.
- Dependency versions are resolved through the committed lockfile.

## Acceptance gate

Phase 0 is accepted only when fresh verification demonstrates all of the
following:

- the package installs from the lockfile in a clean environment;
- `fidelichem --version` and `python -m fidelichem --version` exit successfully;
- the Qt shell starts headlessly and exits without traceback or hanging;
- the full test suite passes with at least 80% branch coverage;
- lint, type checking, build, and dependency checks pass;
- the CI definition covers Windows and Ubuntu with Python 3.12;
- a Terra integration review has no unresolved critical or high findings;
- no scientific domain or persistence implementation has entered the phase.

After the gate, work stops and reports the implemented files, verification
evidence, decisions, risks, acceptance status, and Phase 1 as the next phase.
Phase 1 does not start without a new explicit instruction.

## Risks and reversibility

- Python 3.12 may encounter a future scientific dependency constraint. Recheck
  the chemistry stack before Phase 2; changing the supported minor then is a
  visible packaging decision, not a silent assumption.
- Qt headless behavior differs across operating systems. The two-platform CI
  matrix and process timeouts detect regressions early.
- Codex configuration keys evolve. Validate project-local configuration against
  the active tool schema before committing it.
- Licensing remains deliberately unresolved until a license is chosen before
  the first release, as required by the product plan. Phase 0 must not invent a
  license or copy code/assets from related projects.
