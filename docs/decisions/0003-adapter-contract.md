# ADR 0003: Evidence Adapter SDK and Ingestion Contract

## Context

FideliChem ingests experimental and computational docking evidence (e.g. molecular structures, targets, runs, poses, scores, and source artifacts) from disparate, evolving formats and scientific tools. To maintain long-term architectural integrity and scientific reliability, parsing logic must remain strictly decoupled from persistence, transaction management, and user interfaces.

## Decision

We establish an immutable, storage-agnostic Evidence Adapter SDK and Import Manager contract:

1. **Pure, Decoupled Adapters**:
   Adapters implement the `EvidenceAdapter` protocol (`probe`, `plan`, `parse`, `validate`) returning immutable, frozen Pydantic records (`ImportBundle`). Adapters MUST NOT import SQLAlchemy, connect to databases, or maintain mutable state.
2. **Canonical Domain Separation**:
   Target, compound, molecular state, docking run, pose, score observation, and source artifact are distinct first-class domain models. Missing scientific data (such as omitted scores) is strictly preserved as `None` and NEVER converted silently to zero.
3. **Deterministic Planning & Content-Addressed Hashing**:
   `ImportPlan` captures canonical source file paths and cryptographic SHA-256 digests. The plan hash (`compute_plan_hash`) deterministically identifies the ingestion target.
4. **Duplicate Import Protection**:
   `DuplicateImportDetector` blocks re-ingestion of identical plans or matching artifact sets within completed batches for the same project, while allowing re-import after failed or rolled-back attempts.
5. **Atomic Persistence & Identity Coordination**:
   `ImportManager` coordinates UnitOfWork transactions, persists `ImportBatch` lifecycle states (`in_progress` -> `completed` / `failed` / `rolled_back`), records `SourceArtifact` entries, coordinates chemical identity resolution via `IdentityService`, and generates traceable `AuditEvent` logs.

## Consequences

- **Pros**:
  - Independent testability of parsers without database setup or mocks.
  - Zero risk of partial database writes or orphaned records due to transactional batch boundaries.
  - Full auditability and provenance tracking down to file SHA-256 and source entity references.
  - Third-party extensible through Python `entry_points(group="fidelichem.adapters")`.
- **Cons**:
  - Requires two-stage processing (parsing into in-memory bundle before batch persistence), requiring bounded batch sizes for huge datasets.
