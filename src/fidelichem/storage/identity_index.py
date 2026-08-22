"""Read-only persistent projection for identity-resolution evidence."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy import Engine, exists, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

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
            active = _active_state_exists(_MolecularStateRow.id)
            statement = (
                select(_CompoundRow, _MolecularStateRow, active.label("active"))
                .join(
                    _MolecularStateRow,
                    _MolecularStateRow.compound_id == _CompoundRow.id,
                )
                .where(_MolecularStateRow.state_hash == state_hash)
                .order_by(_CompoundRow.id, _MolecularStateRow.id)
            )
            return _safe_read(
                "molecular state",
                lambda: tuple(
                    _state_candidate(compound, state, bool(is_active))
                    for compound, state, is_active in session.execute(statement)
                ),
            )

        return self._read(query)

    def catalog_by_parent_hash(
        self, parent_hash: str
    ) -> tuple[ResolutionCandidate, ...]:
        def query(session: Session) -> tuple[ResolutionCandidate, ...]:
            active = _active_compound_exists(_CompoundRow.id)
            statement = (
                select(_CompoundRow, active.label("active"))
                .where(_CompoundRow.structure_hash == parent_hash)
                .order_by(_CompoundRow.id)
            )
            return _safe_read(
                "compound",
                lambda: tuple(
                    _compound_candidate(compound, bool(is_active))
                    for compound, is_active in session.execute(statement)
                ),
            )

        return self._read(query)

    def catalog_by_generated_inchikey(
        self, inchikey: str
    ) -> tuple[ResolutionCandidate, ...]:
        def query(session: Session) -> tuple[ResolutionCandidate, ...]:
            compound_active = _active_compound_exists(_CompoundRow.id)
            compound_statement = (
                select(_CompoundRow, compound_active.label("active"))
                .where(_CompoundRow.inchikey == inchikey)
                .order_by(_CompoundRow.id)
            )
            state_active = _active_state_exists(_MolecularStateRow.id)
            state_statement = (
                select(_CompoundRow, _MolecularStateRow, state_active.label("active"))
                .join(
                    _MolecularStateRow,
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
                )
                .join(
                    _AliasRow,
                    _AliasRow.id == _IdentityResolutionRow.alias_id,
                )
                .join(
                    _ImportBatchRow,
                    _ImportBatchRow.id == _AliasRow.import_batch_id,
                )
                .join(
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
                    _IdentityResolutionRow.compound_id.is_not(None),
                )
            )
            successor = _IdentityResolutionRow.__table__.alias("successor")
            statement = statement.where(
                ~exists(
                    select(successor.c.id).where(
                        successor.c.supersedes_id == _IdentityResolutionRow.id
                    )
                ),
                _active_batch_clause(),
            ).order_by(
                _CompoundRow.id,
                _MolecularStateRow.id.is_(None),
                _MolecularStateRow.id,
                _IdentityResolutionRow.id,
            )
            return _safe_read(
                "identity resolution",
                lambda: tuple(
                    _active_candidate(resolution, state)
                    for resolution, state in session.execute(statement)
                ),
            )

        return self._read(query)


def _session_factory_for(engine: Engine) -> SessionFactory:
    from .session import create_session_factory

    return create_session_factory(engine)


def _inchi_candidates(
    session: Session, compound_statement: Any, state_statement: Any
) -> tuple[ResolutionCandidate, ...]:
    candidates = [
        _compound_candidate(
            compound, bool(is_active), evidence=EvidenceKind.CATALOG_INCHI
        )
        for compound, is_active in session.execute(compound_statement)
    ]
    candidates.extend(
        _state_candidate(
            compound,
            state,
            bool(is_active),
            evidence=EvidenceKind.CATALOG_INCHI,
        )
        for compound, state, is_active in session.execute(state_statement)
    )
    return tuple(sorted(candidates, key=lambda item: item.sort_key))


def _active_batch_clause() -> Any:
    return _ImportBatchRow.status != "rolled_back"


def _active_resolution_conditions(resolution_id: Any) -> tuple[Any, ...]:
    successor = _IdentityResolutionRow.__table__.alias("active_successor")
    return (
        _IdentityResolutionRow.decision != "retracted",
        _IdentityResolutionRow.compound_id.is_not(None),
        ~exists(
            select(successor.c.id).where(successor.c.supersedes_id == resolution_id)
        ),
    )


def _active_state_exists(state_id: Any) -> Any:
    return exists(
        select(_IdentityResolutionRow.id)
        .join(_AliasRow, _AliasRow.id == _IdentityResolutionRow.alias_id)
        .join(_ImportBatchRow, _ImportBatchRow.id == _AliasRow.import_batch_id)
        .where(
            _IdentityResolutionRow.molecular_state_id == state_id,
            *_active_resolution_conditions(_IdentityResolutionRow.id),
            _active_batch_clause(),
        )
    )


def _active_compound_exists(compound_id: Any) -> Any:
    return exists(
        select(_IdentityResolutionRow.id)
        .join(_AliasRow, _AliasRow.id == _IdentityResolutionRow.alias_id)
        .join(_ImportBatchRow, _ImportBatchRow.id == _AliasRow.import_batch_id)
        .where(
            _IdentityResolutionRow.compound_id == compound_id,
            *_active_resolution_conditions(_IdentityResolutionRow.id),
            _active_batch_clause(),
        )
    )


def _compound_candidate(
    row: _CompoundRow,
    active: bool,
    *,
    evidence: EvidenceKind = EvidenceKind.CATALOG_PARENT,
) -> ResolutionCandidate:
    return _safe_read(
        "compound",
        lambda: ResolutionCandidate(
            compound_id=row.id,
            evidence=(evidence,),
            catalog_dormant=not active,
        ),
    )


def _state_candidate(
    compound: _CompoundRow,
    state: _MolecularStateRow,
    active: bool,
    *,
    evidence: EvidenceKind = EvidenceKind.CATALOG_STATE,
) -> ResolutionCandidate:
    return _safe_read(
        "molecular state",
        lambda: ResolutionCandidate(
            compound_id=compound.id,
            molecular_state_id=state.id,
            evidence=(evidence,),
            catalog_dormant=not active,
        ),
    )


def _active_candidate(
    resolution: _IdentityResolutionRow,
    state: _MolecularStateRow | None,
) -> ResolutionCandidate:
    def convert() -> ResolutionCandidate:
        if resolution.compound_id is None:
            raise ValueError("missing compound target")
        return ResolutionCandidate(
            compound_id=resolution.compound_id,
            molecular_state_id=None if state is None else state.id,
            resolution_id=resolution.id,
            evidence=(EvidenceKind.ACTIVE_ALIAS,),
            catalog_dormant=False,
        )

    return _safe_read(
        "identity resolution",
        convert,
    )


__all__ = ["PersistentIdentityIndex"]
