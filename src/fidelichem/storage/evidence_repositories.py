"""Append-only repositories for canonical computational evidence.

Evidence records deliberately keep their import-batch and source-artifact
foreign keys next to the scientific values.  This makes every row traceable
without making adapters depend on SQLAlchemy or allowing an adapter to write
outside its caller-owned unit of work.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from fidelichem.domain.adapters import (
    DockingRunRecord,
    InteractionRecord,
    MDMetricRecord,
    MDRunRecord,
    PoseRecord,
    ScoreObservationRecord,
    TargetRecord,
)
from fidelichem.domain.json import canonical_json
from fidelichem.domain.models import ImportStatus
from fidelichem.storage.orm import (
    _DockingRunRow,
    _EvidenceTargetRow,
    _ImportBatchRow,
    _InteractionRow,
    _MDMetricRow,
    _MDRunRow,
    _PoseRow,
    _ScoreObservationRow,
    _SourceArtifactRow,
)

from .repositories import (
    ForeignKeyViolationError,
    _flush,
    _RepositoryBase,
    _safe_read,
)


def _json_mapping(value: Mapping[str, object]) -> str:
    return canonical_json(dict(value))


def _decode_mapping(value: str) -> Mapping[str, object]:
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("stored JSON value is not an object")
    return parsed


class EvidenceRepository(_RepositoryBase):
    """Append-only access to target, docking, interaction, and MD evidence."""

    def __init__(self, session: Session):
        super().__init__(session)

    def _check_parent_batch(self, table: object, entity_id: str, batch_id: str) -> None:
        session = self._require_session()
        row = session.get(table, entity_id)  # type: ignore[arg-type]
        if row is None:
            raise self._missing_parent()
        if getattr(row, "import_batch_id", None) != batch_id:
            raise self._missing_parent()

    @staticmethod
    def _missing_parent() -> ForeignKeyViolationError:
        return ForeignKeyViolationError(
            "evidence parent belongs to another import batch"
        )

    def _check_source_artifact(
        self, source_artifact_id: str | None, import_batch_id: str
    ) -> None:
        if source_artifact_id is not None:
            self._check_parent_batch(
                _SourceArtifactRow, source_artifact_id, import_batch_id
            )

    def add_target(
        self,
        record: TargetRecord,
        *,
        import_batch_id: str,
        source_artifact_id: str | None = None,
    ) -> str:
        self._check_source_artifact(source_artifact_id, import_batch_id)
        row = _EvidenceTargetRow(
            id=_new_id(),
            import_batch_id=import_batch_id,
            source_artifact_id=source_artifact_id,
            name=record.name,
            accession=record.accession,
            pdb_id=record.pdb_id,
            chain=record.chain,
            sequence_hash=record.sequence_hash,
            notes=record.notes,
        )
        _flush(
            self._require_session(), row, entity="evidence target", operation="insert"
        )
        return row.id

    def add_docking_run(
        self,
        record: DockingRunRecord,
        *,
        import_batch_id: str,
        target_id: str | None = None,
        source_artifact_id: str | None = None,
    ) -> str:
        self._check_source_artifact(source_artifact_id, import_batch_id)
        if target_id is not None:
            self._check_parent_batch(_EvidenceTargetRow, target_id, import_batch_id)
        row = _DockingRunRow(
            id=_new_id(),
            import_batch_id=import_batch_id,
            source_artifact_id=source_artifact_id,
            target_id=target_id,
            run_name=record.run_name,
            target_name=record.target_name,
            engine=record.engine,
            engine_version=record.engine_version,
            configuration_hash=record.configuration_hash,
            parameters_json=_json_mapping(record.parameters),
        )
        _flush(self._require_session(), row, entity="docking run", operation="insert")
        return row.id

    def add_pose(
        self,
        record: PoseRecord,
        *,
        import_batch_id: str,
        docking_run_id: str,
        source_artifact_id: str | None = None,
    ) -> str:
        self._check_source_artifact(source_artifact_id, import_batch_id)
        self._check_parent_batch(_DockingRunRow, docking_run_id, import_batch_id)
        row = _PoseRow(
            id=_new_id(),
            import_batch_id=import_batch_id,
            source_artifact_id=source_artifact_id,
            docking_run_id=docking_run_id,
            run_name=record.run_name,
            compound_source_system=record.compound_source_system,
            compound_source_value=record.compound_source_value,
            source_pose_id=record.source_pose_id,
            rank=record.rank,
            structure_artifact_path=record.structure_artifact_path,
            coordinate_hash=record.coordinate_hash,
        )
        _flush(self._require_session(), row, entity="pose", operation="insert")
        return row.id

    def add_score_observation(
        self,
        record: ScoreObservationRecord,
        *,
        import_batch_id: str,
        docking_run_id: str,
        pose_id: str | None = None,
        source_artifact_id: str | None = None,
    ) -> str:
        self._check_source_artifact(source_artifact_id, import_batch_id)
        self._check_parent_batch(_DockingRunRow, docking_run_id, import_batch_id)
        if pose_id is not None:
            self._check_parent_batch(_PoseRow, pose_id, import_batch_id)
        row = _ScoreObservationRow(
            id=_new_id(),
            import_batch_id=import_batch_id,
            source_artifact_id=source_artifact_id,
            docking_run_id=docking_run_id,
            pose_id=pose_id,
            run_name=record.run_name,
            compound_source_value=record.compound_source_value,
            source_pose_id=record.source_pose_id,
            score_key=record.score_key,
            raw_value=record.raw_value,
            source_artifact_path=record.source_artifact_path,
        )
        _flush(
            self._require_session(),
            row,
            entity="score observation",
            operation="insert",
        )
        return row.id

    def add_score(
        self,
        record: ScoreObservationRecord,
        *,
        import_batch_id: str,
        docking_run_id: str,
        pose_id: str | None = None,
        source_artifact_id: str | None = None,
    ) -> str:
        """Compatibility alias for callers that use the bundle field name."""

        return self.add_score_observation(
            record,
            import_batch_id=import_batch_id,
            docking_run_id=docking_run_id,
            pose_id=pose_id,
            source_artifact_id=source_artifact_id,
        )

    def add_interaction(
        self,
        record: InteractionRecord,
        *,
        import_batch_id: str,
        docking_run_id: str | None = None,
        pose_id: str | None = None,
        target_id: str | None = None,
        source_artifact_id: str | None = None,
    ) -> str:
        self._check_source_artifact(source_artifact_id, import_batch_id)
        if docking_run_id is not None:
            self._check_parent_batch(_DockingRunRow, docking_run_id, import_batch_id)
        if pose_id is not None:
            self._check_parent_batch(_PoseRow, pose_id, import_batch_id)
        if target_id is not None:
            self._check_parent_batch(_EvidenceTargetRow, target_id, import_batch_id)
        row = _InteractionRow(
            id=_new_id(),
            import_batch_id=import_batch_id,
            source_artifact_id=source_artifact_id,
            docking_run_id=docking_run_id,
            pose_id=pose_id,
            target_id=target_id,
            run_name=record.run_name,
            compound_source_value=record.compound_source_value,
            source_pose_id=record.source_pose_id,
            residue_name=record.residue_name,
            interaction_type=record.interaction_type,
            target_name=record.target_name,
            residue_number=record.residue_number,
            chain=record.chain,
            distance=record.distance,
            angle=record.angle,
            energy=record.energy,
            frequency=record.frequency,
            ligand_feature=record.ligand_feature,
            metadata_json=_json_mapping(record.metadata),
        )
        _flush(self._require_session(), row, entity="interaction", operation="insert")
        return row.id

    def add_md_run(
        self,
        record: MDRunRecord,
        *,
        import_batch_id: str,
        target_id: str | None = None,
        pose_id: str | None = None,
        source_artifact_id: str | None = None,
    ) -> str:
        self._check_source_artifact(source_artifact_id, import_batch_id)
        if target_id is not None:
            self._check_parent_batch(_EvidenceTargetRow, target_id, import_batch_id)
        if pose_id is not None:
            self._check_parent_batch(_PoseRow, pose_id, import_batch_id)
        row = _MDRunRow(
            id=_new_id(),
            import_batch_id=import_batch_id,
            source_artifact_id=source_artifact_id,
            target_id=target_id,
            pose_id=pose_id,
            run_name=record.run_name,
            target_name=record.target_name,
            compound_source_value=record.compound_source_value,
            source_pose_id=record.source_pose_id,
            duration_ns=record.duration_ns,
            temperature_k=record.temperature_k,
            timestep_fs=record.timestep_fs,
            engine=record.engine,
            engine_version=record.engine_version,
            parameters_json=_json_mapping(record.parameters),
        )
        _flush(self._require_session(), row, entity="MD run", operation="insert")
        return row.id

    def add_md_metric(
        self,
        record: MDMetricRecord,
        *,
        import_batch_id: str,
        md_run_id: str,
        source_artifact_id: str | None = None,
    ) -> str:
        self._check_source_artifact(source_artifact_id, import_batch_id)
        self._check_parent_batch(_MDRunRow, md_run_id, import_batch_id)
        row = _MDMetricRow(
            id=_new_id(),
            import_batch_id=import_batch_id,
            source_artifact_id=source_artifact_id,
            md_run_id=md_run_id,
            run_name=record.run_name,
            metric_key=record.metric_key,
            unit=record.unit,
            mean_value=record.mean_value,
            std_value=record.std_value,
            min_value=record.min_value,
            max_value=record.max_value,
            compound_source_value=record.compound_source_value,
            source_pose_id=record.source_pose_id,
            source_artifact_path=record.source_artifact_path,
            time_points_json=canonical_json(list(record.time_points)),
            values_json=canonical_json(list(record.values)),
            metadata_json=_json_mapping(record.metadata),
        )
        _flush(self._require_session(), row, entity="MD metric", operation="insert")
        return row.id

    def list_targets(self, import_batch_id: str) -> tuple[TargetRecord, ...]:
        session = self._require_session()
        statement = (
            select(_EvidenceTargetRow)
            .where(_EvidenceTargetRow.import_batch_id == import_batch_id)
            .order_by(_EvidenceTargetRow.name, _EvidenceTargetRow.id)
        )
        return _safe_read(
            "evidence targets",
            lambda: tuple(
                _target_model(row) for row in session.execute(statement).scalars()
            ),
        )

    def list_docking_runs(self, import_batch_id: str) -> tuple[DockingRunRecord, ...]:
        session = self._require_session()
        statement = (
            select(_DockingRunRow)
            .where(_DockingRunRow.import_batch_id == import_batch_id)
            .order_by(_DockingRunRow.run_name, _DockingRunRow.id)
        )
        return _safe_read(
            "docking runs",
            lambda: tuple(
                _docking_run_model(row) for row in session.execute(statement).scalars()
            ),
        )

    def list_poses(self, import_batch_id: str) -> tuple[PoseRecord, ...]:
        session = self._require_session()
        statement = (
            select(_PoseRow)
            .where(_PoseRow.import_batch_id == import_batch_id)
            .order_by(_PoseRow.run_name, _PoseRow.rank, _PoseRow.id)
        )
        return _safe_read(
            "poses",
            lambda: tuple(
                _pose_model(row) for row in session.execute(statement).scalars()
            ),
        )

    def list_scores(self, import_batch_id: str) -> tuple[ScoreObservationRecord, ...]:
        session = self._require_session()
        statement = (
            select(_ScoreObservationRow)
            .where(_ScoreObservationRow.import_batch_id == import_batch_id)
            .order_by(
                _ScoreObservationRow.run_name,
                _ScoreObservationRow.source_pose_id,
                _ScoreObservationRow.score_key,
                _ScoreObservationRow.id,
            )
        )
        return _safe_read(
            "score observations",
            lambda: tuple(
                _score_model(row) for row in session.execute(statement).scalars()
            ),
        )

    def list_interactions(self, import_batch_id: str) -> tuple[InteractionRecord, ...]:
        session = self._require_session()
        statement = (
            select(_InteractionRow)
            .where(_InteractionRow.import_batch_id == import_batch_id)
            .order_by(
                _InteractionRow.run_name,
                _InteractionRow.source_pose_id,
                _InteractionRow.residue_name,
                _InteractionRow.id,
            )
        )
        return _safe_read(
            "interactions",
            lambda: tuple(
                _interaction_model(row) for row in session.execute(statement).scalars()
            ),
        )

    def list_md_runs(self, import_batch_id: str) -> tuple[MDRunRecord, ...]:
        session = self._require_session()
        statement = (
            select(_MDRunRow)
            .where(_MDRunRow.import_batch_id == import_batch_id)
            .order_by(_MDRunRow.run_name, _MDRunRow.id)
        )
        return _safe_read(
            "MD runs",
            lambda: tuple(
                _md_run_model(row) for row in session.execute(statement).scalars()
            ),
        )

    def list_md_metrics(self, import_batch_id: str) -> tuple[MDMetricRecord, ...]:
        session = self._require_session()
        statement = (
            select(_MDMetricRow)
            .where(_MDMetricRow.import_batch_id == import_batch_id)
            .order_by(_MDMetricRow.run_name, _MDMetricRow.metric_key, _MDMetricRow.id)
        )
        return _safe_read(
            "MD metrics",
            lambda: tuple(
                _md_metric_model(row) for row in session.execute(statement).scalars()
            ),
        )

    def list_export_records(
        self,
        project_id: str,
        *,
        include_scores: bool = True,
        include_interactions: bool = True,
        include_dynamics: bool = True,
        include_provenance: bool = True,
    ) -> tuple[Mapping[str, Any], ...]:
        """Return a deterministic, read-only export snapshot for a project.

        Only completed import batches are eligible.  Every row carries its
        batch identifier and canonical evidence family, preserving the
        minimum provenance needed by export consumers without exposing ORM
        rows or allowing the GUI to issue SQL queries.
        """

        session = self._require_session()
        statement = (
            select(_ImportBatchRow)
            .where(
                _ImportBatchRow.project_id == project_id,
                _ImportBatchRow.status == ImportStatus.COMPLETED.value,
            )
            .order_by(_ImportBatchRow.started_at, _ImportBatchRow.id)
        )

        def build() -> tuple[Mapping[str, Any], ...]:
            batches = session.execute(statement).scalars().all()
            records: list[Mapping[str, Any]] = []
            for batch in batches:
                families = [
                    ("target", self.list_targets(batch.id)),
                    ("docking_run", self.list_docking_runs(batch.id)),
                    ("pose", self.list_poses(batch.id)),
                ]
                if include_scores:
                    families.append(("score", self.list_scores(batch.id)))
                if include_interactions:
                    families.append(("interaction", self.list_interactions(batch.id)))
                if include_dynamics:
                    families.extend(
                        (
                            ("md_run", self.list_md_runs(batch.id)),
                            ("md_metric", self.list_md_metrics(batch.id)),
                        )
                    )
                for evidence_type, values in families:
                    records.extend(
                        _export_record(
                            batch_id=batch.id,
                            evidence_type=evidence_type,
                            payload=value.model_dump(mode="json"),
                            include_provenance=include_provenance,
                        )
                        for value in values
                    )
            return tuple(records)

        return _safe_read("export evidence", build)


def _export_record(
    *,
    batch_id: str,
    evidence_type: str,
    payload: Mapping[str, Any],
    include_provenance: bool,
) -> Mapping[str, Any]:
    record = {"evidence_type": evidence_type, **payload}
    if include_provenance:
        return {"import_batch_id": batch_id, **record}
    return record


def _new_id() -> str:
    from fidelichem.domain.ids import new_id

    return new_id()


def _target_model(row: _EvidenceTargetRow) -> TargetRecord:
    return _safe_read(
        "evidence target",
        lambda: TargetRecord(
            name=row.name,
            accession=row.accession,
            pdb_id=row.pdb_id,
            chain=row.chain,
            sequence_hash=row.sequence_hash,
            notes=row.notes,
        ),
    )


def _docking_run_model(row: _DockingRunRow) -> DockingRunRecord:
    return _safe_read(
        "docking run",
        lambda: DockingRunRecord(
            run_name=row.run_name,
            target_name=row.target_name,
            engine=row.engine,
            engine_version=row.engine_version,
            configuration_hash=row.configuration_hash,
            parameters=_decode_mapping(row.parameters_json),
        ),
    )


def _pose_model(row: _PoseRow) -> PoseRecord:
    return _safe_read(
        "pose",
        lambda: PoseRecord(
            run_name=row.run_name,
            compound_source_system=row.compound_source_system,
            compound_source_value=row.compound_source_value,
            source_pose_id=row.source_pose_id,
            rank=row.rank,
            structure_artifact_path=row.structure_artifact_path,
            coordinate_hash=row.coordinate_hash,
        ),
    )


def _score_model(row: _ScoreObservationRow) -> ScoreObservationRecord:
    return _safe_read(
        "score observation",
        lambda: ScoreObservationRecord(
            run_name=row.run_name,
            compound_source_value=row.compound_source_value,
            source_pose_id=row.source_pose_id,
            score_key=row.score_key,
            raw_value=row.raw_value,
            source_artifact_path=row.source_artifact_path,
        ),
    )


def _interaction_model(row: _InteractionRow) -> InteractionRecord:
    return _safe_read(
        "interaction",
        lambda: InteractionRecord(
            run_name=row.run_name,
            compound_source_value=row.compound_source_value,
            source_pose_id=row.source_pose_id,
            residue_name=row.residue_name,
            interaction_type=row.interaction_type,
            target_name=row.target_name,
            residue_number=row.residue_number,
            chain=row.chain,
            distance=row.distance,
            angle=row.angle,
            energy=row.energy,
            frequency=row.frequency,
            ligand_feature=row.ligand_feature,
            metadata=_decode_mapping(row.metadata_json),
        ),
    )


def _md_run_model(row: _MDRunRow) -> MDRunRecord:
    return _safe_read(
        "MD run",
        lambda: MDRunRecord(
            run_name=row.run_name,
            target_name=row.target_name,
            compound_source_value=row.compound_source_value,
            source_pose_id=row.source_pose_id,
            duration_ns=row.duration_ns,
            temperature_k=row.temperature_k,
            timestep_fs=row.timestep_fs,
            engine=row.engine,
            engine_version=row.engine_version,
            parameters=_decode_mapping(row.parameters_json),
        ),
    )


def _md_metric_model(row: _MDMetricRow) -> MDMetricRecord:
    def convert() -> MDMetricRecord:
        time_points = json.loads(row.time_points_json)
        values = json.loads(row.values_json)
        if not isinstance(time_points, list) or not isinstance(values, list):
            raise ValueError("stored MD metric series is not an array")
        return MDMetricRecord(
            run_name=row.run_name,
            metric_key=row.metric_key,
            unit=row.unit,
            mean_value=row.mean_value,
            std_value=row.std_value,
            min_value=row.min_value,
            max_value=row.max_value,
            compound_source_value=row.compound_source_value,
            source_pose_id=row.source_pose_id,
            source_artifact_path=row.source_artifact_path,
            time_points=tuple(time_points),
            values=tuple(values),
            metadata=_decode_mapping(row.metadata_json),
        )

    return _safe_read("MD metric", convert)


__all__ = ["EvidenceRepository"]
