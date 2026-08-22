"""Transaction-bound repositories for chemistry and identity rows."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from fidelichem.domain.chemistry import (
    Alias,
    Compound,
    IdentityDecision,
    IdentityResolution,
    MolecularState,
)
from fidelichem.domain.errors import AliasConflictError, IdentityResolutionConflictError
from fidelichem.domain.models import ActorKind

from .orm import (
    _AliasRow,
    _CompoundRow,
    _IdentityResolutionRow,
    _MolecularStateRow,
)
from .repositories import (
    DuplicateRecordError,
    ForeignKeyViolationError,
    RepositoryError,
    StorageIntegrityError,
    StorageWriteError,
    _fail_transaction,
    _RepositoryBase,
    _safe_read,
)


def _chemistry_integrity(
    error: IntegrityError,
    *,
    entity: str,
) -> RepositoryError | AliasConflictError | IdentityResolutionConflictError:
    detail = str(error.orig).lower()
    if "foreign key" in detail:
        return ForeignKeyViolationError(f"{entity} references a missing parent")
    if entity == "alias":
        if (
            "unique constraint failed: alias.import_batch_id, alias.source_system, "
            "alias.source_value" in detail
        ):
            return AliasConflictError()
        if "unique constraint failed: alias.id" in detail:
            return DuplicateRecordError("alias already exists")
    if entity == "identity resolution":
        conflict_markers = (
            "identity resolution root must be confirmed",
            "identity resolution predecessor alias mismatch",
            "identity resolution predecessor already has successor",
            "identity resolution state ownership mismatch",
            "identity resolution transition is invalid",
            "identity resolution restore is invalid",
        )
        if any(marker in detail for marker in conflict_markers):
            return IdentityResolutionConflictError()
        if (
            "unique constraint failed: identity_resolution.alias_id" in detail
            or "unique constraint failed: identity_resolution.supersedes_id" in detail
        ):
            return IdentityResolutionConflictError()
        if "unique constraint failed: identity_resolution.id" in detail:
            return DuplicateRecordError("identity resolution already exists")
    if "unique" in detail or "primary key" in detail:
        return DuplicateRecordError(f"{entity} already exists")
    return StorageIntegrityError(f"{entity} violates storage integrity")


def _flush_chemistry(session: Session, row: object, *, entity: str) -> None:
    try:
        session.add(row)
        session.flush()
    except IntegrityError as error:
        _fail_transaction(session)
        raise _chemistry_integrity(error, entity=entity) from None
    except SQLAlchemyError:
        _fail_transaction(session)
        raise StorageWriteError(
            f"{entity} write failed due to a storage error"
        ) from None


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


def _alias_model(row: _AliasRow) -> Alias:
    return _safe_read(
        "alias",
        lambda: Alias(
            id=row.id,
            source_system=row.source_system,
            source_value=row.source_value,
            import_batch_id=row.import_batch_id,
            created_at=row.created_at,
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


class _ChemistryRepositoryBase(_RepositoryBase):
    def _read[ModelT](self, entity: str, operation: Callable[[], ModelT]) -> ModelT:
        self._require_session()
        return _safe_read(entity, operation)


class CompoundRepository(_ChemistryRepositoryBase):
    """Append-only compound repository."""

    def add(self, compound: Compound) -> Compound:
        session = self._require_session()
        row = _CompoundRow(
            id=compound.id,
            canonical_smiles=compound.canonical_smiles,
            isomeric_smiles=compound.isomeric_smiles,
            inchikey=compound.inchikey,
            formula=compound.formula,
            molecular_weight=compound.molecular_weight,
            structure_hash=compound.structure_hash,
            chemistry_policy_id=compound.chemistry_policy_id,
            rdkit_version=compound.rdkit_version,
            inchi_version=compound.inchi_version,
            created_at=compound.created_at,
        )
        _flush_chemistry(session, row, entity="compound")
        return _compound_model(row)

    def get(self, compound_id: str) -> Compound | None:
        session = self._require_session()
        return self._read(
            "compound",
            lambda: (
                lambda row: None if row is None else _compound_model(row)
            )(session.get(_CompoundRow, compound_id)),
        )

    def get_by_structure_hash(self, structure_hash: str) -> Compound | None:
        session = self._require_session()
        statement = select(_CompoundRow).where(
            _CompoundRow.structure_hash == structure_hash
        )
        return self._read(
            "compound",
            lambda: (lambda row: None if row is None else _compound_model(row))(
                session.execute(statement).scalar_one_or_none()
            ),
        )


class MolecularStateRepository(_ChemistryRepositoryBase):
    """Append-only molecular-state repository."""

    def add(self, state: MolecularState) -> MolecularState:
        session = self._require_session()
        row = _MolecularStateRow(
            id=state.id,
            compound_id=state.compound_id,
            state_smiles=state.state_smiles,
            state_inchikey=state.state_inchikey,
            formal_charge=state.formal_charge,
            stereochemistry_signature=state.stereochemistry_signature,
            protonation_signature=state.protonation_signature,
            tautomer_signature=state.tautomer_signature,
            state_hash=state.state_hash,
            chemistry_policy_id=state.chemistry_policy_id,
            rdkit_version=state.rdkit_version,
            inchi_version=state.inchi_version,
            preparation_ph=state.preparation_ph,
        )
        _flush_chemistry(session, row, entity="molecular state")
        return _state_model(row)

    def get(self, state_id: str) -> MolecularState | None:
        session = self._require_session()
        return self._read(
            "molecular state",
            lambda: (
                lambda row: None if row is None else _state_model(row)
            )(session.get(_MolecularStateRow, state_id)),
        )

    def get_by_state_hash(self, state_hash: str) -> MolecularState | None:
        session = self._require_session()
        statement = select(_MolecularStateRow).where(
            _MolecularStateRow.state_hash == state_hash
        )
        return self._read(
            "molecular state",
            lambda: (lambda row: None if row is None else _state_model(row))(
                session.execute(statement).scalar_one_or_none()
            ),
        )


class AliasRepository(_ChemistryRepositoryBase):
    """Append-only source-alias repository."""

    def add(self, alias: Alias) -> Alias:
        session = self._require_session()
        row = _AliasRow(
            id=alias.id,
            source_system=alias.source_system,
            source_value=alias.source_value,
            import_batch_id=alias.import_batch_id,
            created_at=alias.created_at,
        )
        _flush_chemistry(session, row, entity="alias")
        return _alias_model(row)

    def get(self, alias_id: str) -> Alias | None:
        session = self._require_session()
        return self._read(
            "alias",
            lambda: (
                lambda row: None if row is None else _alias_model(row)
            )(session.get(_AliasRow, alias_id)),
        )

    def list_by_batch(self, batch_id: str) -> tuple[Alias, ...]:
        session = self._require_session()
        statement = (
            select(_AliasRow)
            .where(_AliasRow.import_batch_id == batch_id)
            .order_by(_AliasRow.source_system, _AliasRow.source_value, _AliasRow.id)
        )
        return self._read(
            "alias",
            lambda: tuple(
                _alias_model(row) for row in session.execute(statement).scalars()
            ),
        )

    def get_by_source(
        self, batch_id: str, source_system: str, source_value: str
    ) -> Alias | None:
        session = self._require_session()
        statement = select(_AliasRow).where(
            _AliasRow.import_batch_id == batch_id,
            _AliasRow.source_system == source_system,
            _AliasRow.source_value == source_value,
        )
        return self._read(
            "alias",
            lambda: (lambda row: None if row is None else _alias_model(row))(
                session.execute(statement).scalar_one_or_none()
            ),
        )


class IdentityResolutionRepository(_ChemistryRepositoryBase):
    """Append-only identity-decision repository."""

    def add(self, resolution: IdentityResolution) -> IdentityResolution:
        session = self._require_session()
        row = _IdentityResolutionRow(
            id=resolution.id,
            alias_id=resolution.alias_id,
            decision=resolution.decision.value,
            compound_id=resolution.compound_id,
            molecular_state_id=resolution.molecular_state_id,
            supersedes_id=resolution.supersedes_id,
            decided_at=resolution.decided_at,
            actor_kind=resolution.actor_kind.value,
            actor_id=resolution.actor_id,
            rationale=resolution.rationale,
        )
        _flush_chemistry(session, row, entity="identity resolution")
        return _resolution_model(row)

    def get(self, resolution_id: str) -> IdentityResolution | None:
        session = self._require_session()
        return self._read(
            "identity resolution",
            lambda: (
                lambda row: None if row is None else _resolution_model(row)
            )(session.get(_IdentityResolutionRow, resolution_id)),
        )

    def list_by_alias(self, alias_id: str) -> tuple[IdentityResolution, ...]:
        session = self._require_session()
        statement = (
            select(_IdentityResolutionRow)
            .where(_IdentityResolutionRow.alias_id == alias_id)
            .order_by(_IdentityResolutionRow.decided_at, _IdentityResolutionRow.id)
        )
        return self._read(
            "identity resolution",
            lambda: tuple(
                _resolution_model(row) for row in session.execute(statement).scalars()
            ),
        )

    def list_all(self) -> tuple[IdentityResolution, ...]:
        session = self._require_session()
        statement = select(_IdentityResolutionRow).order_by(
            _IdentityResolutionRow.decided_at, _IdentityResolutionRow.id
        )
        return self._read(
            "identity resolution",
            lambda: tuple(
                _resolution_model(row) for row in session.execute(statement).scalars()
            ),
        )


__all__ = [
    "AliasRepository",
    "CompoundRepository",
    "IdentityResolutionRepository",
    "MolecularStateRepository",
]
