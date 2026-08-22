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
- MDRunRecord and MDMetricRecord domain models for molecular dynamics simulation parameters and analytical metrics.
- GROMACS XVG analytical curve parser (`parse_xvg`) extracting multi-series curves, legends, units, and summary statistics (min, max, mean, std).
- GROMACS Evidence Adapter (`GromacsAdapter`) parsing RMSD, RMSF, Radius of Gyration, SASA, and energy curves.
- MolDynStudio Evidence Adapter (`MolDynStudioAdapter`) ingesting simulation manifests, trajectory parameters, and time-series metrics.
- Score consensus engine (`compute_score_consensus`) calculating percentile medians, weighted averages, and rank dispersions across arbitrary scoring functions with missing data preservation.
- Scoring agreement metrics (`compute_molecule_agreement`, `compute_campaign_agreement`) calculating Spearman and Kendall rank correlations, top-k Jaccard overlap, and per-candidate agreement levels (HIGH, MODERATE, LOW).
- Multi-objective Pareto optimization (`compute_pareto_fronts`) executing fast non-dominated sorting across multi-dimensional criteria with strict directionality and non-destructive missing data handling.
- Unified `AnalyticsEngine` facade coordinating multi-fidelity scoring, agreement, and Pareto analytics.
- Symmetry-corrected in-situ and aligned 3D pose RMSD calculation in `ChemistryService` via topological automorphism matching.
- Pairwise 3D pose RMSD matrix generation across multi-conformer and docking solution sets.
- Butina-based structural pose clustering (`cluster_poses`) with exact centroid medoid determination minimizing intra-cluster RMSD distance.
- Structural pose consensus evaluation (`compute_pose_consensus`) determining dominant binding mode families, stability scores, and agreement levels.
- Interaction prevalence analytics (`InteractionPrevalence`) quantifying contact frequencies, mean/min distances, and angles across conformers with zero-contact denominator preservation.
- Residue-by-interaction-type cross-tabulation matrix generation across campaign candidates.
- Pose family interaction profiling (`PoseFamilyInteractionProfile`) characterizing conserved vs cluster-specific binding interactions.
- Core interaction conservation analysis (`compute_interaction_consensus`) identifying critical active-site anchoring contacts.
- Versioned Decision Profile domain schema (`DecisionProfile`, `DecisionCriterion`) with typed criteria roles (`exclusion`, `mandatory`, `rank`, `warning`, `informative`).
- Multi-fidelity candidate evaluation engine (`evaluate_compound_decision`, `evaluate_campaign_decisions`) computing composite scores and triage priorities (`ADVANCE`, `HOLD`, `REJECT`, `INSUFFICIENT_DATA`).
- Transparent justification generation providing structured `why_positive`, `why_negative`, and warnings for every evaluated molecule.
- Next Best Evidence recommendation engine directing targeted follow-up calculations (MD simulations, interaction profiling, secondary docking) for held candidates.












### Changed

- Conflicting identity evidence is never silently auto-merged; confirmation
  remains report-bound and requires an explicit user choice when applicable.
