# FideliChem Phase 3 Adapter SDK and Import Manager Design

## Status and dependency gate

**Status: queued. Do not implement until Phase 2 gate is verified.**

This specification narrows Phase 3 of `FideliChem_PLANO_CODEX.md`. Phases 1 and 2
provide the storage foundation, provenance, project lifecycle, chemistry
canonicalization, and auditable identity resolution core.

Phase 3 introduces the universal Adapter SDK and the Import Manager, establishing
the single authoritative pipeline through which external scientific data enters
a FideliChem project.

## Goal and architectural principles

1. **Adapters never write to storage directly**:
   Adapters only inspect input files, generate immutable plans, parse raw data
   into canonical bundles, and run domain validation. The `ImportManager` is the
   sole component authorized to persist data and manage transactions.

2. **Immutability of evidence and plans**:
   - `ImportPlan` is immutable, deterministic, and content-hashed.
   - `ImportBundle` contains only canonical data representations. Raw evidence is
     never mutated or silently modified.
   - Missing numerical data is never silently converted to zero.

3. **Pluggable and extensible architecture**:
   - Adapters implement the `EvidenceAdapter` protocol.
   - Adapters are registered in an `AdapterRegistry`, which supports static
     registration and discovery via Python entry points (`fidelichem.adapters`).

4. **Deterministic identity resolution integration**:
   - Chemical items in an `ImportBundle` are resolved and confirmed through the
     Phase 2 `IdentityService` / `IdentityResolver` pipeline.
   - No silent merging occurs.

5. **Duplicate import detection and provenance safety**:
   - Before executing an import, the system verifies whether the input files
     or identical plan have already been imported into an active completed batch.
   - Every imported file is verified against its disk checksum (SHA-256) and
     recorded as an immutable `SourceArtifact`.

6. **Transactional atomic import and logical rollback**:
   - Every import executes in a single Unit of Work / transaction.
   - A batch starts as `in_progress`. On success, it transitions to `completed`
     with an atomic `AuditEvent`.
   - On error, changes are rolled back, and the batch is recorded as `failed`
     with diagnostic audit events without leaving orphan records.
   - Reversible logical rollback preserves the audit trail and raw artifacts
     while retracting active claims.

## Core contracts and data structures

### 1. Adapter Protocol (`EvidenceAdapter`)

```python
class EvidenceAdapter(Protocol):
    adapter_id: str
    adapter_version: str
    display_name: str

    def probe(self, source: Path) -> DetectionReport:
        """Inspect source path and return detection confidence and format metadata."""
        ...

    def plan(
        self, source: Path, options: Mapping[str, Any] | None = None
    ) -> ImportPlan:
        """Create an immutable, content-hashed import plan from source and options."""
        ...

    def parse(self, plan: ImportPlan) -> ImportBundle:
        """Parse source files described in the plan into a canonical import bundle."""
        ...

    def validate(self, bundle: ImportBundle) -> ValidationReport:
        """Validate canonical bundle for semantic correctness and QC issues."""
        ...
```

### 2. Detection and Planning Models

- **`DetectionReport`**:
  - `confidence: float` (0.0 to 1.0)
  - `detected_format: str`
  - `candidate_files: tuple[str, ...]`
  - `warnings: tuple[str, ...]`
  - `requires_user_mapping: bool`
  - `suggested_adapter: str`
  - `extra_metadata: Mapping[str, Any]`

- **`ImportPlan`**:
  - `id: OpaqueId`
  - `adapter_id: str`
  - `adapter_version: str`
  - `source_root: str`
  - `source_files: tuple[str, ...]`
  - `file_hashes: tuple[tuple[str, Sha256Digest], ...]`
  - `options: Mapping[str, Any]`
  - `created_at: UtcTimestamp`
  - `plan_hash: Sha256Digest`

### 3. Canonical Bundle Items (`ImportBundle`)

- **`RawCompoundRecord`**:
  - `source_system: str`
  - `source_value: str`
  - `source_smiles: str | None = None`
  - `source_inchikey: str | None = None`
  - `preparation_ph: float | None = None`
  - `source_artifact_path: str | None = None`
  - `metadata: Mapping[str, Any] = Field(default_factory=dict)`

- **`TargetRecord`**:
  - `name: str`
  - `accession: str | None = None`
  - `pdb_id: str | None = None`
  - `chain: str | None = None`
  - `sequence_hash: str | None = None`
  - `notes: str | None = None`

- **`DockingRunRecord`**:
  - `run_name: str`
  - `target_name: str | None = None`
  - `engine: str`
  - `engine_version: str | None = None`
  - `configuration_hash: str | None = None`
  - `parameters: Mapping[str, Any] = Field(default_factory=dict)`

- **`PoseRecord`**:
  - `run_name: str`
  - `compound_source_system: str`
  - `compound_source_value: str`
  - `source_pose_id: str`
  - `rank: int`
  - `structure_artifact_path: str | None = None`
  - `coordinate_hash: str | None = None`

- **`ScoreObservationRecord`**:
  - `run_name: str`
  - `compound_source_value: str`
  - `source_pose_id: str`
  - `score_key: str`
  - `raw_value: float`
  - `source_artifact_path: str | None = None`

- **`SourceArtifactRecord`**:
  - `relative_path: str`
  - `sha256: Sha256Digest`
  - `size_bytes: int`
  - `file_type: str`
  - `mtime: UtcTimestamp | None = None`

- **`QCIssue`**:
  - `code: str`
  - `message: str`
  - `severity: QCSeverity` (`INFO`, `WARNING`, `ERROR`)
  - `source_file: str | None = None`
  - `line_number: int | None = None`
  - `entity_reference: str | None = None`

- **`ValidationReport`**:
  - `is_valid: bool`
  - `errors: tuple[str, ...]`
  - `warnings: tuple[str, ...]`
  - `qc_issues: tuple[QCIssue, ...]`

- **`ImportBundle`**:
  - `plan: ImportPlan`
  - `targets: tuple[TargetRecord, ...]`
  - `compounds: tuple[RawCompoundRecord, ...]`
  - `docking_runs: tuple[DockingRunRecord, ...]`
  - `poses: tuple[PoseRecord, ...]`
  - `scores: tuple[ScoreObservationRecord, ...]`
  - `source_artifacts: tuple[SourceArtifactRecord, ...]`
  - `qc_messages: tuple[QCIssue, ...]`
  - `provenance: Mapping[str, Any]`

### 4. Adapter Registry (`AdapterRegistry`)

- Maintains registered adapter instances.
- Discovers entry points via `importlib.metadata.entry_points(group="fidelichem.adapters")`.
- Exposes `probe_all(source: Path)` returning a tuple of `DetectionReport` sorted by confidence descending.

### 5. Import Manager (`ImportManager`)

- Orchestrates end-to-end import flow:
  1. `detect(source: Path) -> tuple[DetectionReport, ...]`
  2. `plan(adapter_id: str, source: Path, options: Mapping[str, Any] | None = None) -> ImportPlan`
  3. `execute_import(project_path: Path, plan: ImportPlan, dry_run: bool = False, actor: IdentityActor | None = None, failpoint: Callable[[str], None] | None = None) -> ImportResult`
  4. `rollback_import(project_path: Path, batch_id: str, reason: str, actor: IdentityActor | None = None) -> ImportBatch`

- **Duplicate Detection**:
  - Checks if a completed, active `ImportBatch` with identical `input_hash` or matching `SourceArtifact` SHA-256 set exists in the project.
  - Raises `DuplicateImportError` with existing batch details.

- **Atomic Execution**:
  - Uses `UnitOfWork` to:
    - Create `ImportBatch` with status `in_progress`.
    - Persist `SourceArtifact` items.
    - Process chemical records through `ChemistryService` and `IdentityService` to confirm claims and link aliases.
    - Transition `ImportBatch` to `completed` and write `AuditEvent(IMPORT_COMPLETED)`.
  - Catches failpoints and errors to roll back the UoW, mark batch as `failed` (if batch created), and record `AuditEvent(IMPORT_FAILED)`.

### 6. Reference FakeAdapter (`FakeAdapter`)

- Complete implementation of `EvidenceAdapter` protocol used to test the full pipeline, edge cases, duplicate rejection, validation failures, atomic rollback, and re-importing.
