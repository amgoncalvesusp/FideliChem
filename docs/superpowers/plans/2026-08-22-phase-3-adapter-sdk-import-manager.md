# FideliChem Phase 3 Adapter SDK and Import Manager Implementation Plan

> **Execution gate:** Execute only after Phase 2 gate is verified.
> **Methodology:** Every production behavior follows RED-GREEN-REFACTOR. Minimum 80% branch coverage required.

**Goal:** Deliver a pluggable, deterministic Adapter SDK and transactional Import Manager that standardizes external scientific evidence into canonical bundles, prevents duplicate imports, resolves chemical identities via `IdentityService`, and guarantees atomic persistence and reversible rollback.

**Architecture:**
- `EvidenceAdapter` protocol defines `probe()`, `plan()`, `parse()`, and `validate()`.
- `AdapterRegistry` manages adapter discovery via code and `importlib.metadata.entry_points`.
- `ImportManager` coordinates planning, validation, duplicate checking, and atomic database persistence.
- Identity claims within bundles are passed to `IdentityService` to confirm compounds/states/aliases without silent merging.
- Database transactions start with `ImportBatch(in_progress)` and finish with `completed` + `AuditEvent`.
- `FakeAdapter` exercises the complete pipeline as a reference implementation.

**Spec:** `docs/superpowers/specs/2026-08-22-phase-3-adapter-sdk-import-manager-design.md`

## File structure and serial ownership

| Area | Files |
| --- | --- |
| Domain models & QC | `src/fidelichem/domain/adapters.py`, `src/fidelichem/domain/errors.py`, `src/fidelichem/domain/__init__.py` |
| Adapter SDK | `src/fidelichem/adapters/__init__.py`, `src/fidelichem/adapters/base.py`, `src/fidelichem/adapters/registry.py` |
| Import Manager & Pipeline | `src/fidelichem/importers/__init__.py`, `src/fidelichem/importers/duplicate_detector.py`, `src/fidelichem/importers/manager.py` |
| Fake Adapter reference | `src/fidelichem/adapters/fake.py` |
| Tests | `tests/unit/domain/test_adapter_models.py`, `tests/unit/adapters/test_registry.py`, `tests/integration/importers/test_import_manager.py`, `tests/integration/importers/test_import_pipeline.py` |
| Documentation | `docs/decisions/0003-adapter-contract.md`, `docs/implementation-status.md` |

---

### Task 1: Domain models for adapters, detection, planning, QC, validation, and bundles

**Files:**
- Modify: `src/fidelichem/domain/errors.py`
- Modify: `src/fidelichem/domain/__init__.py`
- Create: `src/fidelichem/domain/adapters.py`
- Create: `tests/unit/domain/test_adapter_models.py`

**Consumes:** `DomainModel`, `OpaqueId`, `Sha256Digest`, `UtcTimestamp`, `ActorKind`.
**Produces:** `DetectionReport`, `ImportPlan`, `QCSeverity`, `QCIssue`, `ValidationReport`, `RawCompoundRecord`, `TargetRecord`, `DockingRunRecord`, `PoseRecord`, `ScoreObservationRecord`, `SourceArtifactRecord`, `ImportBundle`, `ImportResult`, typed error classes (`DuplicateImportError`, `ImportValidationError`, `AdapterNotFoundError`).

- [ ] **Step 1: Write failing tests for adapter domain models and errors.**
- [ ] **Step 2: Implement domain models with strict validation, frozen configuration, and deterministic hashing.**
- [ ] **Step 3: Run pytest, mypy, and ruff to verify models.**

---

### Task 2: Universal EvidenceAdapter protocol and base utilities

**Files:**
- Create: `src/fidelichem/adapters/__init__.py`
- Create: `src/fidelichem/adapters/base.py`
- Create: `tests/unit/adapters/test_base_adapter.py`

**Consumes:** Adapter domain models from Task 1.
**Produces:** `EvidenceAdapter` protocol, base helper functions for source path scanning and file hashing.

- [ ] **Step 1: Write failing tests for EvidenceAdapter protocol enforcement and helpers.**
- [ ] **Step 2: Implement protocol and hashing/scanning utilities.**
- [ ] **Step 3: Verify with tests and static typecheck.**

---

### Task 3: Adapter registry and dynamic entry-point discovery

**Files:**
- Create: `src/fidelichem/adapters/registry.py`
- Create: `tests/unit/adapters/test_registry.py`

**Consumes:** `EvidenceAdapter`, `DetectionReport`.
**Produces:** `AdapterRegistry` with `register()`, `get()`, `list_adapters()`, `discover_entry_points()`, and `probe_all()`.

- [ ] **Step 1: Write failing tests for registry operations, error handling, entry-point discovery, and probe ranking.**
- [ ] **Step 2: Implement `AdapterRegistry`.**
- [ ] **Step 3: Verify with unit tests.**

---

### Task 4: Duplicate import detector and file provenance validator

**Files:**
- Create: `src/fidelichem/importers/__init__.py`
- Create: `src/fidelichem/importers/duplicate_detector.py`
- Create: `tests/unit/importers/test_duplicate_detector.py`

**Consumes:** `ImportPlan`, `StorageService` / repositories, `DuplicateImportError`.
**Produces:** `DuplicateImportDetector` verifying active completed batches and matching input hashes or source artifact sets.

- [ ] **Step 1: Write failing tests for duplicate import detection against completed/failed/rolled_back batches.**
- [ ] **Step 2: Implement `DuplicateImportDetector`.**
- [ ] **Step 3: Verify with unit tests.**

---

### Task 5: Import Manager service with atomic persistence and identity integration

**Files:**
- Create: `src/fidelichem/importers/manager.py`
- Create: `tests/integration/importers/test_import_manager.py`

**Consumes:** `AdapterRegistry`, `DuplicateImportDetector`, `IdentityService`, `ChemistryService`, `StorageService`, `UnitOfWork`.
**Produces:** `ImportManager` implementing `detect()`, `plan()`, and `execute_import()` with atomic batch creation, source artifact tracking, chemical identity confirmation, and failure rollback.

- [ ] **Step 1: Write failing integration tests for import execution, validation errors, identity claim confirmation, failpoints, and atomicity.**
- [ ] **Step 2: Implement `ImportManager.execute_import()`.**
- [ ] **Step 3: Verify integration tests and coverage.**

---

### Task 6: Rollback orchestration and lifecycle integration

**Files:**
- Modify: `src/fidelichem/importers/manager.py`
- Modify: `tests/integration/importers/test_import_manager.py`

**Consumes:** `StorageService.rollback_batch`, `ImportBatch`.
**Produces:** `ImportManager.rollback_import()` orchestrating logical rollback, provenance preservation, and audit trail.

- [ ] **Step 1: Write failing tests for import rollback and subsequent re-import behavior.**
- [ ] **Step 2: Implement rollback orchestration in `ImportManager`.**
- [ ] **Step 3: Verify rollback tests.**

---

### Task 7: Reference FakeAdapter and complete end-to-end acceptance pipeline

**Files:**
- Create: `src/fidelichem/adapters/fake.py`
- Create: `tests/integration/importers/test_import_pipeline.py`

**Consumes:** `EvidenceAdapter`, `ImportManager`, `FakeAdapter`.
**Produces:** Full pipeline acceptance tests (probe -> plan -> parse -> validate -> execute_import -> duplicate_rejection -> rollback -> re_import).

- [ ] **Step 1: Implement `FakeAdapter` emitting canonical bundle with artifacts, compounds, scores, and QC messages.**
- [ ] **Step 2: Write comprehensive end-to-end acceptance tests verifying all acceptance criteria for Phase 3.**
- [ ] **Step 3: Run full suite with branch coverage >= 80%.**

---

### Task 8: Architectural documentation, ADR, and Phase 3 verification gate

**Files:**
- Create: `docs/decisions/0003-adapter-contract.md`
- Modify: `docs/implementation-status.md`
- Modify: `CHANGELOG.md`
- Modify: `README.md`

- [ ] **Step 1: Record ADR 0003 for universal adapter contract and Import Manager boundary.**
- [ ] **Step 2: Run full gate checks (`uv lock --check`, Ruff, mypy, pip-audit, uv build, pytest with coverage >= 80%).**
- [ ] **Step 3: Update `docs/implementation-status.md` and project changelog.**
