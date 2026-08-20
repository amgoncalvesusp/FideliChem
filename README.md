# FideliChem

FideliChem is an explainable multi-fidelity molecular evidence and decision
platform. The repository is currently at Phase 0: the tested CLI and desktop
application shell. No scientific evidence model or adapter is implemented yet.

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

The full product architecture and phased roadmap are documented in
`FideliChem_PLANO_CODEX.md`.
