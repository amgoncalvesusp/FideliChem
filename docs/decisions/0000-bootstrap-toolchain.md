# ADR 0000: Phase 0 bootstrap toolchain

- Status: Accepted
- Date: 2026-08-19

## Context

FideliChem needs a reproducible Windows and Ubuntu desktop bootstrap before any
scientific domain or storage decisions are implemented.

## Decision

Use Python 3.12, uv with a committed lockfile, Hatchling as the build backend,
PySide6 as the only runtime dependency, and pytest-based tests with 80% minimum
branch coverage. Defer all scientific dependencies and PyInstaller packaging to
the phases that first need them.

## Consequences

The initial compatibility surface stays small and CI can validate the real CLI
and Qt shell on both target operating systems. Python 3.12 compatibility with
the future chemistry stack must be rechecked before Phase 2; changing the
Python minor then requires an explicit ADR and lockfile regeneration.
