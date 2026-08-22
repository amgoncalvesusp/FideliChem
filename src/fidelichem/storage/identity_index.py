"""Read-only persistent projection for identity-resolution evidence."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy import Engine, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from fidelichem.domain.chemistry import (
    Compound,
    IdentityDecision,
    IdentityResolution,
    MolecularState,
)
from fidelichem.domain.models import ActorKind
from fidelichem.identity.models import (
    EvidenceKind,
    ResolutionCandidate,
)

from .orm import (
    _AliasRow,
    _CompoundRow,
    _IdentityResolutionRow,
    _ImportBatchRow,
    _MolecularStateRow,
)
from .repositories import (
    CorruptStoredDataError,
    RepositoryError,
    StorageReadError,
    _safe_read,
)
from .session import SessionFactory


class PersistentIdentityIndex:
    """SELECT-only implementation of the identity evidence index."""

    def __init__(self, source: Engine | SessionFactory):
        self._session_factory = (
            _session_factory_for(source) if isinstance(source, Engine) else source
        )

    def _read[ResultT](self, operation: Callable[[Session], ResultT]) -> ResultT:
        try:
            return self._with_session(operation)
        except RepositoryError:
            raise
        except Exception as error:
            if isinstance(error, SQLAlchemyError):
                raise StorageReadError(
                    "identity index read failed due to a storage error"
                ) from None
            raise CorruptStoredDataError(
                "stored identity index data is invalid"
            ) from None

    def _with_session[ResultT](
        self, operation: Callable[[Session], ResultT]
    ) -> ResultT:
        with self._session_factory() as session:
            return operation(session)

    def catalog_by_state_hash(
        self, state_hash: str
    ) -> tuple[ResolutionCandidate, ...]:
        def query(session: Session) -> tuple[ResolutionCandidate, ...]:
            statement = (
                select(_MolecularStateRow, _CompoundRow)
                .outerjoin(
                    _CompoundRow,
                    _MolecularStateRow.compound_id == _CompoundRow.id,
                )
                .where(_MolecularStateRow.state_hash == state_hash)
                .order_by(_CompoundRow.id, _MolecularStateRow.id)
            )
            return _safe_read(
                "molecular state",
                lambda: tuple(
                    _state_candidate(
                        compound,
                        state,
                        _catalog_state_active(session, state.id),
                    )
                    for state, compound in session.execute(statement)
                ),
            )

        return self._read(query)

    def catalog_by_parent_hash(
        self, parent_hash: str
    ) -> tuple[ResolutionCandidate, ...]:
        def query(session: Session) -> tuple[ResolutionCandidate, ...]:
            statement = (
                select(_CompoundRow)
                .where(_CompoundRow.structure_hash == parent_hash)
                .order_by(_CompoundRow.id)
            )
            return _safe_read(
                "compound",
                lambda: tuple(
                    _compound_candidate(
                        compound,
                        _catalog_compound_active(session, compound.id),
                    )
                    for (compound,) in session.execute(statement)
                ),
            )

        return self._read(query)

    def catalog_by_generated_inchikey(
        self, inchikey: str
    ) -> tuple[ResolutionCandidate, ...]:
        def query(session: Session) -> tuple[ResolutionCandidate, ...]:
            compound_statement = (
                select(_CompoundRow)
                .where(_CompoundRow.inchikey == inchikey)
                .order_by(_CompoundRow.id)
            )
            state_statement = (
                select(_MolecularStateRow, _CompoundRow)
                .outerjoin(
                    _CompoundRow,
                    _MolecularStateRow.compound_id == _CompoundRow.id,
                )
                .where(_MolecularStateRow.state_inchikey == inchikey)
                .order_by(_CompoundRow.id, _MolecularStateRow.id)
            )
            return _safe_read(
                "compound",
                lambda: _inchi_candidates(
                    session, compound_statement, state_statement
                ),
            )

        return self._read(query)

    def active_by_alias(
        self, source_system: str, source_value: str
    ) -> tuple[ResolutionCandidate, ...]:
        def query(session: Session) -> tuple[ResolutionCandidate, ...]:
            statement = (
                select(
                    _IdentityResolutionRow,
                    _MolecularStateRow,
                    _CompoundRow,
                    _ImportBatchRow,
                )
                .join(
                    _AliasRow,
                    _AliasRow.id == _IdentityResolutionRow.alias_id,
                )
                .join(
                    _ImportBatchRow,
                    _ImportBatchRow.id == _AliasRow.import_batch_id,
                )
                .outerjoin(
                    _CompoundRow,
                    _CompoundRow.id == _IdentityResolutionRow.compound_id,
                )
                .outerjoin(
                    _MolecularStateRow,
                    _MolecularStateRow.id
                    == _IdentityResolutionRow.molecular_state_id,
                )
                .where(
                    _AliasRow.source_system == source_system,
                    _AliasRow.source_value == source_value,
                    _IdentityResolutionRow.decision != "retracted",
                )
            )
            statement = statement.order_by(
                _CompoundRow.id,
                _MolecularStateRow.id.is_(None),
                _MolecularStateRow.id,
                _IdentityResolutionRow.id,
            )
            return _safe_read(
                "identity resolution",
                lambda: _active_alias_candidates(session, statement),
            )

        return self._read(query)


def _active_alias_candidates(
    session: Session, statement: Any
) -> tuple[ResolutionCandidate, ...]:
    rows = tuple(session.execute(statement))
    validated: dict[str, tuple[Any, Any, Any, Any, IdentityResolution]] = {}
    superseded_ids: set[str] = set()
    for resolution, state, compound, batch in rows:
        resolution_value = _validate_resolution_row(session, resolution)
        _validate_batch_status(batch.status)
        validated[resolution.id] = (
            resolution,
            state,
            compound,
            batch,
            resolution_value,
        )
    for resolution, _, _, _, _ in validated.values():
        successors = _successors(session, resolution.id)
        if successors:
            superseded_ids.add(resolution.id)
        for successor, successor_batch in successors:
            _validate_batch_status(successor_batch.status)
            _validate_resolution_row(session, successor)
    candidates = []
    for resolution, state, compound, batch, resolution_value in validated.values():
        if (
            resolution_value.decision is not IdentityDecision.RETRACTED
            and resolution_value.compound_id is not None
            and batch.status in {"in_progress", "completed", "failed"}
            and resolution.id not in superseded_ids
        ):
            candidates.append(_active_candidate(resolution, state, compound))
    return tuple(sorted(candidates, key=lambda item: item.sort_key))


def _session_factory_for(engine: Engine) -> SessionFactory:
    from .session import create_session_factory

    return create_session_factory(engine)


def _inchi_candidates(
    session: Session, compound_statement: Any, state_statement: Any
) -> tuple[ResolutionCandidate, ...]:
    candidates = [
        _compound_candidate(
            compound,
            _catalog_compound_active(session, compound.id),
            evidence=EvidenceKind.CATALOG_INCHI,
        )
        for (compound,) in session.execute(compound_statement)
    ]
    candidates.extend(
        _state_candidate(
            compound,
            state,
            _catalog_state_active(session, state.id),
            evidence=EvidenceKind.CATALOG_INCHI,
        )
        for state, compound in session.execute(state_statement)
    )
    return tuple(sorted(candidates, key=lambda item: item.sort_key))


def _catalog_state_active(session: Session, state_id: str) -> bool:
    statement = (
        select(_IdentityResolutionRow, _ImportBatchRow)
        .join(_AliasRow, _AliasRow.id == _IdentityResolutionRow.alias_id)
        .join(_ImportBatchRow, _ImportBatchRow.id == _AliasRow.import_batch_id)
        .where(_IdentityResolutionRow.molecular_state_id == state_id)
    )
    return _catalog_target_active(session, statement)


def _catalog_compound_active(session: Session, compound_id: str) -> bool:
    statement = (
        select(_IdentityResolutionRow, _ImportBatchRow)
        .join(_AliasRow, _AliasRow.id == _IdentityResolutionRow.alias_id)
        .join(_ImportBatchRow, _ImportBatchRow.id == _AliasRow.import_batch_id)
        .where(_IdentityResolutionRow.compound_id == compound_id)
    )
    return _catalog_target_active(session, statement)


def _catalog_target_active(session: Session, statement: Any) -> bool:
    contributors = tuple(session.execute(statement))
    active = False
    for resolution, batch in contributors:
        resolution_value = _validate_resolution_row(session, resolution)
        successors = _successors(session, resolution.id)
        if successors:
            active_successor = True
            for successor, successor_batch in successors:
                _validate_batch_status(successor_batch.status)
                _validate_resolution_row(session, successor)
        else:
            active_successor = False
        _validate_batch_status(batch.status)
        if (
            resolution_value.decision is not IdentityDecision.RETRACTED
            and resolution_value.compound_id is not None
            and batch.status in {"in_progress", "completed", "failed"}
            and not active_successor
        ):
            active = True
    return active


def _successors(
    session: Session, resolution_id: str
) -> tuple[tuple[_IdentityResolutionRow, _ImportBatchRow], ...]:
    statement = (
        select(_IdentityResolutionRow, _ImportBatchRow)
        .join(_AliasRow, _AliasRow.id == _IdentityResolutionRow.alias_id)
        .join(_ImportBatchRow, _ImportBatchRow.id == _AliasRow.import_batch_id)
        .where(_IdentityResolutionRow.supersedes_id == resolution_id)
    )
    return tuple(session.execute(statement).tuples().all())


def _validate_batch_status(status: str) -> None:
    if status not in {"in_progress", "completed", "failed", "rolled_back"}:
        raise CorruptStoredDataError("stored identity resolution data is invalid")


def _validate_resolution_row(
    session: Session, row: _IdentityResolutionRow
) -> IdentityResolution:
    resolution = _resolution_model(row)
    compound = None
    if resolution.compound_id is not None:
        compound_row = session.get(_CompoundRow, resolution.compound_id)
        if compound_row is None:
            raise CorruptStoredDataError("stored identity resolution data is invalid")
        compound = _compound_model(compound_row)
    if resolution.molecular_state_id is not None:
        state_row = session.get(_MolecularStateRow, resolution.molecular_state_id)
        if state_row is None:
            raise CorruptStoredDataError("stored identity resolution data is invalid")
        state = _state_model(state_row)
        if compound is None or state.compound_id != compound.id:
            raise CorruptStoredDataError("stored identity resolution data is invalid")
    return resolution


def _compound_candidate(
    row: _CompoundRow,
    active: bool,
    *,
    evidence: EvidenceKind = EvidenceKind.CATALOG_PARENT,
) -> ResolutionCandidate:
    compound = _compound_model(row)
    return _safe_read(
        "compound",
        lambda: ResolutionCandidate(
            compound_id=compound.id,
            evidence=(evidence,),
            catalog_dormant=not active,
        ),
    )


def _state_candidate(
    compound: _CompoundRow | None,
    state: _MolecularStateRow,
    active: bool,
    *,
    evidence: EvidenceKind = EvidenceKind.CATALOG_STATE,
) -> ResolutionCandidate:
    if compound is None:
        raise CorruptStoredDataError("stored molecular state data is invalid")
    compound_value = _compound_model(compound)
    state_value = _state_model(state)
    if state_value.compound_id != compound_value.id:
        raise CorruptStoredDataError("stored molecular state data is invalid")
    return _safe_read(
        "molecular state",
        lambda: ResolutionCandidate(
            compound_id=compound_value.id,
            molecular_state_id=state_value.id,
            evidence=(evidence,),
            catalog_dormant=not active,
        ),
    )


def _compound_model(row: _CompoundRow) -> Compound:
    return _safe_read(
        "compound",
        lambda: Compound(
            id=row.id,
            canonical_smiles=row.canonical_smiles,
            isomeric_smiles=row.isomeric_smiles,
            inchikey=row.inchikey,
            formula=row.formula,
            molecular_weight=row.molecular_weight,
            structure_hash=row.structure_hash,
            chemistry_policy_id=row.chemistry_policy_id,
            rdkit_version=row.rdkit_version,
            inchi_version=row.inchi_version,
            created_at=row.created_at,
        ),
    )


def _state_model(row: _MolecularStateRow) -> MolecularState:
    return _safe_read(
        "molecular state",
        lambda: MolecularState(
            id=row.id,
            compound_id=row.compound_id,
            state_smiles=row.state_smiles,
            state_inchikey=row.state_inchikey,
            formal_charge=row.formal_charge,
            stereochemistry_signature=row.stereochemistry_signature,
            protonation_signature=row.protonation_signature,
            tautomer_signature=row.tautomer_signature,
            state_hash=row.state_hash,
            chemistry_policy_id=row.chemistry_policy_id,
            rdkit_version=row.rdkit_version,
            inchi_version=row.inchi_version,
            preparation_ph=row.preparation_ph,
        ),
    )


def _resolution_model(row: _IdentityResolutionRow) -> IdentityResolution:
    return _safe_read(
        "identity resolution",
        lambda: IdentityResolution(
            id=row.id,
            alias_id=row.alias_id,
            decision=IdentityDecision(row.decision),
            compound_id=row.compound_id,
            molecular_state_id=row.molecular_state_id,
            supersedes_id=row.supersedes_id,
            decided_at=row.decided_at,
            actor_kind=ActorKind(row.actor_kind),
            actor_id=row.actor_id,
            rationale=row.rationale,
        ),
    )


def _active_candidate(
    resolution: _IdentityResolutionRow,
    state: _MolecularStateRow | None,
    compound: _CompoundRow | None,
) -> ResolutionCandidate:
    def convert() -> ResolutionCandidate:
        resolution_value = _resolution_model(resolution)
        if compound is None:
            raise ValueError("resolution compound target is missing")
        compound_value = _compound_model(compound)
        if resolution_value.compound_id is None:
            raise ValueError("missing compound target")
        if resolution_value.compound_id != compound_value.id:
            raise ValueError("resolution target does not match compound")
        state_value = None if state is None else _state_model(state)
        if resolution_value.molecular_state_id is not None and state_value is None:
            raise ValueError("resolution state target is missing")
        if (
            state_value is not None
            and state_value.compound_id != resolution_value.compound_id
        ):
            raise ValueError("resolution state target does not match compound")
        return ResolutionCandidate(
            compound_id=compound_value.id,
            molecular_state_id=None if state_value is None else state_value.id,
            resolution_id=resolution_value.id,
            evidence=(EvidenceKind.ACTIVE_ALIAS,),
            catalog_dormant=False,
        )

    return _safe_read(
        "identity resolution",
        convert,
    )


__all__ = ["PersistentIdentityIndex"]
