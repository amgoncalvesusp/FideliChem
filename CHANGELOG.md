# Changelog

All notable changes to FideliChem will be documented in this file.

## Unreleased

### Added

- Reproducible Python 3.12 project bootstrap.
- Versioned CLI and domain-free PySide6 application shell.
- Operational logging, automated tests, CI, and Codex agent roles.
- Safe project creation and reopening with canonical manifests, migrated
  SQLite storage, read-only access, and bounded failure cleanup.
- Versioned RDKit chemistry identity with map-cleared exact states, bounded
  parentization, optional InChI evidence, and conservative salt/co-crystal
  handling.
- Persistent catalog/active-alias identity projections, report-authorized
  atomic confirmations, batch-correlated audit events, and reversible
  reassign/retract/restore chains.

### Changed

- Conflicting identity evidence is never silently auto-merged; confirmation
  remains report-bound and requires an explicit user choice when applicable.
