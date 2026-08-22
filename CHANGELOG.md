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
- Pure EvidenceAdapter SDK protocol, AdapterRegistry with discovery and confidence ranking.
- Immutable adapter domain models (DetectionReport, ImportPlan, QCIssue, ValidationReport, RawCompoundRecord, TargetRecord, DockingRunRecord, PoseRecord, ScoreObservationRecord, ImportBundle, ImportResult).
- DuplicateImportDetector enforcing deduplication on completed project batches while permitting re-import after rollback/failure.
- ImportManager orchestrating discovery, validation, chemical identity confirmation, and atomic persistence.
- Fake reference adapter and end-to-end acceptance pipeline test suite.
- Universal Table Importer domain models (ColumnRole, ScoreDirection, ScoreScope, ScoreColumnMapping, IdentityColumnMapping, TableMappingSchema, TableMappingPreset).
- Robust tabular file inspection and readers supporting CSV, TSV, JSON, and JSONL with strict missing data preservation (None instead of zero).
- PresetManager for saving, loading, listing, and heuristic header matching of reusable mapping templates.
- UniversalTableAdapter implementing EvidenceAdapter with full integration into ImportManager and chemical identity resolution.
- ScoreDefinition domain model with explicit comparability scopes, units, and directionality.
- ScoreRegistry service with catalog of standard docking scoring functions (ChemPLP, GoldScore, ChemScore, ASP, Vina affinity, Glide, etc.) and heuristic direction inference.
- ScoreNormalizer computing direction-aware percentiles (oriented with 1.0 = best candidate), ranks, robust Z-scores via MAD, and scope distribution statistics with strict missing data preservation.




### Changed

- Conflicting identity evidence is never silently auto-merged; confirmation
  remains report-bound and requires an explicit user choice when applicable.
