# FideliChem

FideliChem is an explainable multi-fidelity molecular evidence and decision
platform. The current foundation includes persistent, portable project roots,
immutable provenance records, transactional storage, and audited import-batch
lifecycle operations. Scientific adapters are added in later phases.

Author: Adriano Marques Gonçalves (UNIARA)

The FideliChem source code is available under the MIT License. Third-party
runtime components retain their own licenses; see
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

## Requirements

- Python 3.12
- uv 0.11 or newer

## Bootstrap

```powershell
uv sync --locked --group dev
uv run fidelichem --version
$env:QT_QPA_PLATFORM='offscreen'
uv run fidelichem-gui
```

## Verification

```powershell
uv lock --check
uv run ruff check .
uv run mypy src/fidelichem
uv run pytest --cov=fidelichem --cov-branch --cov-report=term-missing --cov-fail-under=80
uv run pip-audit
uv build
uv pip check
```

## Release installers (v0.1.1)

Each tagged release publishes self-contained desktop installers for Windows
and Linux. Download the matching asset from the GitHub release page
and verify it before running it with `SHA256SUMS.txt`.

- Windows installer: run `FideliChem-0.1.1-Windows-x64-Setup.exe` to install
  shortcuts and an uninstall entry.
- Windows portable: extract `FideliChem-0.1.1-Windows-x64.zip` and run
  `FideliChem.exe`.
- Linux portable: extract `FideliChem-0.1.1-Linux-x64.tar.gz` and run
  `./FideliChem/FideliChem`.
- Debian/Ubuntu: install `FideliChem-0.1.1-Linux-x64.deb` with
  `sudo dpkg -i FideliChem-0.1.1-Linux-x64.deb`, then launch
  `fidelichem-gui`.

The release also includes the Python wheel and source distribution for
development installations.

## Persistent projects

Create or reopen a project directory with the safe layout service:

```python
from fidelichem.projects import create_project, open_project

created = create_project("my-project", "My project")
created.close()

opened = open_project("my-project", read_only=True)
try:
    print(opened.project.id, opened.database)
finally:
    opened.close()
```

Project creation writes a canonical UTF-8 `project.json`, migrates
`project.fidelichem.sqlite`, and creates `artifacts/`, `cache/`, `exports/`,
and `logs/`. Existing project roots are never overwritten; read-only opening
uses SQLite's `mode=ro` connection.

## Chemistry identity (Phase 2)

The chemistry boundary uses RDKit 2026.3.4 and a versioned, bounded policy.
`Compound` records a parent family while `MolecularState` preserves the exact
map-cleared state, including stereo, charge, tautomer, and disconnected
components. One-organic salts are supported; co-crystals and other
multi-organic structures require explicit future policy. Optional InChIKey
evidence is nullable and warnings are included in the same audit event as an
identity confirmation.

Identity resolution is read-only until an explicit report-authorized
confirmation. Structural catalog rows remain reusable after alias retraction
or import rollback, while inactive alias projections are hidden. Ambiguous or
conflicting evidence is never silently merged. See
[`docs/decisions/0002-compound-vs-state.md`](docs/decisions/0002-compound-vs-state.md)
and [`docs/decisions/0005-identity-resolution.md`](docs/decisions/0005-identity-resolution.md)
for the frozen boundaries and non-goals.

The full product architecture and phased roadmap are documented in
`FideliChem_PLANO_CODEX.md`.
