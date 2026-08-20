# FideliChem

FideliChem is an explainable multi-fidelity molecular evidence and decision
platform. The current foundation includes persistent, portable project roots,
immutable provenance records, transactional storage, and audited import-batch
lifecycle operations. Scientific adapters are added in later phases.

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

The full product architecture and phased roadmap are documented in
`FideliChem_PLANO_CODEX.md`.
