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
- CCDC GOLD Evidence Adapter (`GoldAdapter`) for automated detection, planning, and parsing of docking directories and solution files.
- GOLD configuration and parameter parser (`gold.conf` / `gold.params`), ranking list parser (`bestranking.lst`, `gold_ranking.txt`, `ranking.csv`), and multi-molecule TRIPOS MOL2 solution parser (`gold_soln_*.mol2`).
- Multi-scoring extraction preserving distinct observations for ChemPLP, GoldScore, ChemScore, ASP, and additional rescores across multiple runs without cross-contamination.
- GOLD QC issue diagnostic reporting for duplicate pose IDs, missing solution files, and incomplete runs.
- SMILES2Select Evidence Adapter (`Smiles2SelectAdapter`) parsing compound selection campaigns from SQLite, JSON, and CSV with selection decisions, QED, SA score, and physicochemical properties.
- SMILES2Docking Evidence Adapter (`Smiles2DockingAdapter`) parsing 3D ligand preparation runs, target pH protonation states, energy minimization methods, and structural artifact links.
- Cross-evidence identity resolution pipeline enabling continuous tracking from selection filtering through ligand preparation to docking poses under a unified chemical compound identity.
- InteractionRecord domain model for mechanistic interactions with standard (`target|residue|type`) and granular (`target|residue|type|feature`) interaction keys.
- DockLens Evidence Adapter (`DockLensAdapter`) parsing mechanistic contacts, distances, angles, occupancies/frequencies, and scientific interaction profiles from JSON and CSV.
- Mechanistic interaction linkage associating DockLens contacts directly to docking poses (e.g. GOLD Pose P003) and MD trajectories.







### Changed

- Conflicting identity evidence is never silently auto-merged; confirmation
  remains report-bound and requires an explicit user choice when applicable.
