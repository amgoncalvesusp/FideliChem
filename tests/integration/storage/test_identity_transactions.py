from __future__ import annotations

from contextlib import suppress
from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine, text

from fidelichem.domain.chemistry import Compound
from fidelichem.domain.models import ImportBatch, Project
from fidelichem.storage.repositories import ForeignKeyViolationError
from fidelichem.storage.session import (
    UnitOfWork,
    UnitOfWorkError,
    create_session_factory,
)

NOW = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)


def _project() -> Project:
    return Project(name="Project", created_at=NOW, updated_at=NOW)


def _batch(project_id: str) -> ImportBatch:
    return ImportBatch(
        project_id=project_id,
        adapter_id="adapter",
        adapter_version="1",
        started_at=NOW,
        source_root="inputs",
    )


def _compound() -> Compound:
    return Compound(
        canonical_smiles="CCO",
        isomeric_smiles="CCO",
        formula="C2H6O",
        molecular_weight=46.069,
        structure_hash="a" * 64,
        chemistry_policy_id="fidelichem.rdkit-identity.v1",
        rdkit_version="2026.3.4",
        created_at=NOW,
    )


def test_identity_uow_rolls_back_prior_chemistry_writes_after_fk_failure(
    migrated_engine: Engine,
) -> None:
    factory = create_session_factory(migrated_engine)
    with pytest.raises(ForeignKeyViolationError), UnitOfWork(factory) as uow:
        uow.compounds.add(_compound())
        uow.import_batches.add(_batch("99999999-9999-4999-8999-999999999999"))

    with factory() as session:
        assert session.execute(text("SELECT count(*) FROM compound")).scalar_one() == 0


def test_identity_uow_repositories_fail_closed_after_swallowed_conflict(
    migrated_engine: Engine,
) -> None:
    with pytest.raises(UnitOfWorkError, match="failed"), UnitOfWork(
        migrated_engine
    ) as uow:
        project = _project()
        uow.projects.add(project)
        uow.compounds.add(_compound())
        with suppress(ForeignKeyViolationError):
            uow.import_batches.add(_batch("99999999-9999-4999-8999-999999999999"))
        with pytest.raises(UnitOfWorkError, match="failed"):
            uow.compounds.get("99999999-9999-4999-8999-999999999999")


def test_chemistry_repository_reference_is_inactive_after_uow_exit(
    migrated_engine: Engine,
) -> None:
    with UnitOfWork(migrated_engine) as uow:
        compounds = uow.compounds
    with pytest.raises(UnitOfWorkError, match="inactive"):
        compounds.get("99999999-9999-4999-8999-999999999999")
