"""Integration and end-to-end acceptance tests for UniversalTableAdapter."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from fidelichem.adapters.registry import AdapterRegistry
from fidelichem.adapters.table import PresetManager, UniversalTableAdapter
from fidelichem.chemistry.service import ChemistryService
from fidelichem.domain.chemistry import (
    IdentityActor,
    IdentityDecision,
)
from fidelichem.domain.errors import (
    DuplicateImportError,
)
from fidelichem.domain.models import (
    ActorKind,
    ImportStatus,
    Project,
)
from fidelichem.domain.table_importer import (
    IdentityColumnMapping,
    ScoreColumnMapping,
    ScoreDirection,
    TableMappingPreset,
    TableMappingSchema,
)
from fidelichem.identity.service import IdentityService
from fidelichem.importers.manager import ImportManager
from fidelichem.storage.engine import create_sqlite_engine
from fidelichem.storage.identity_index import PersistentIdentityIndex
from fidelichem.storage.runner import upgrade_database
from fidelichem.storage.session import UnitOfWork


@pytest.fixture
def table_pipeline_env(tmp_path: Path):
    db_path = tmp_path / "project.fidelichem.sqlite"
    engine = create_sqlite_engine(db_path)
    upgrade_database(engine)

    def _uow_factory() -> UnitOfWork:
        return UnitOfWork(engine)

    def _index_factory() -> PersistentIdentityIndex:
        return PersistentIdentityIndex(engine)

    def clock() -> datetime:
        return datetime(2026, 8, 22, 12, 0, 0, tzinfo=UTC)

    identity_service = IdentityService(
        uow_factory=_uow_factory,
        index_factory=_index_factory,
        clock=clock,
    )
    chemistry_service = ChemistryService()

    registry = AdapterRegistry()
    registry.register(UniversalTableAdapter())

    manager = ImportManager(
        registry=registry,
        uow_factory=_uow_factory,
        identity_service=identity_service,
        chemistry_service=chemistry_service,
        clock=clock,
    )

    now = datetime(2026, 8, 22, 12, 0, 0, tzinfo=UTC)
    with _uow_factory() as uow:
        project = uow.projects.add(
            Project(name="Table Pipeline Test", created_at=now, updated_at=now)
        )

    data_dir = tmp_path / "data"
    data_dir.mkdir()

    try:
        yield manager, project.id, data_dir, _uow_factory, _index_factory
    finally:
        engine.dispose()


def test_universal_table_csv_e2e(table_pipeline_env) -> None:
    manager, project_id, data_dir, uow_factory, index_factory = table_pipeline_env

    # 1. Create CSV file with 3 compounds and 2 score metrics
    csv_file = data_dir / "screen_results.csv"
    csv_file.write_text(
        "Ligand_ID,Structure_SMILES,Score_PLP,Score_Gold,Note\n"
        "LIG_01,CC(=O)Oc1ccccc1C(=O)O,84.5,-12.3,hit\n"
        "LIG_02,CC(=O)Nc1ccc(O)cc1,72.1,-9.8,moderate\n"
        "LIG_03,c1ccccc1,,,\n",  # Missing both scores
        encoding="utf-8",
    )

    # 2. Probe
    reports = manager.detect(data_dir)
    assert len(reports) >= 1
    table_rep = next(
        r for r in reports if r.suggested_adapter == "fidelichem.universal_table"
    )
    assert table_rep.confidence >= 0.8
    assert "screen_results.csv" in table_rep.candidate_files

    # 3. Plan with TableMappingSchema
    schema = TableMappingSchema(
        identity=IdentityColumnMapping(
            molecule_id_column="Ligand_ID",
            smiles_column="Structure_SMILES",
            source_system_default="in_house_assay",
            target_name_default="COX-2",
            run_name_default="VirtualScreen_01",
        ),
        scores=(
            ScoreColumnMapping(
                column_name="Score_PLP",
                score_key="docking.plp",
                direction=ScoreDirection.HIGHER_BETTER,
            ),
            ScoreColumnMapping(
                column_name="Score_Gold",
                score_key="docking.gold",
                direction=ScoreDirection.LOWER_BETTER,
            ),
        ),
    )

    plan = manager.plan(
        "fidelichem.universal_table",
        data_dir,
        options={"schema": schema.model_dump(mode="json")},
    )

    # 4. Ingest via ImportManager
    actor = IdentityActor(kind=ActorKind.USER, actor_id="bioinformatician_1")
    result = manager.execute_import(project_id, plan, actor=actor)

    assert result.batch.status == ImportStatus.COMPLETED
    assert len(result.confirmed_resolutions) == 3
    for res in result.confirmed_resolutions:
        assert res.decision is IdentityDecision.CONFIRMED

    # 5. Verify database records
    with uow_factory() as uow:
        # Batch verification
        batch = uow.import_batches.get(result.batch.id)
        assert batch is not None
        assert batch.status == ImportStatus.COMPLETED

        # Artifacts verification
        artifacts = uow.source_artifacts.list_by_batch(result.batch.id)
        assert len(artifacts) == 1
        assert artifacts[0].relative_path == "screen_results.csv"

        # Chemical aliases
        aliases = uow.aliases.list_by_batch(result.batch.id)
        assert len(aliases) == 3
        alias_names = {a.source_value for a in aliases}
        assert alias_names == {"LIG_01", "LIG_02", "LIG_03"}

        # Audit history
        events = uow.audit_events.list_by_batch(result.batch.id)
        assert any(e.action == "import.completed" for e in events)

    # 6. Index query verification
    index = index_factory()
    active_l1 = index.active_by_alias("in_house_assay", "LIG_01")
    assert len(active_l1) >= 1
    assert active_l1[0].compound_id is not None

    # 7. Duplicate prevention
    with pytest.raises(DuplicateImportError, match="Duplicate import detected"):
        manager.execute_import(project_id, plan)

    # 8. Rollback and re-import
    rolled_back = manager.rollback_import(
        project_id, result.batch.id, reason="Correction of docking weights", actor=actor
    )
    assert rolled_back.status == ImportStatus.ROLLED_BACK

    # Re-import identical plan succeeds after rollback
    reimport_res = manager.execute_import(project_id, plan, actor=actor)
    assert reimport_res.batch.status == ImportStatus.COMPLETED
    assert reimport_res.batch.id != result.batch.id


def test_universal_table_preset_workflow(table_pipeline_env, tmp_path: Path) -> None:
    manager, project_id, data_dir, uow_factory, index_factory = table_pipeline_env

    # 1. Create Preset
    now = datetime(2026, 8, 22, 12, 0, 0, tzinfo=UTC)
    schema = TableMappingSchema(
        identity=IdentityColumnMapping(
            molecule_id_column="id",
            smiles_column="smiles",
            source_system_default="lab_hatch",
        ),
        scores=(
            ScoreColumnMapping(
                column_name="chem_score",
                score_key="screening.chem_score",
                direction=ScoreDirection.HIGHER_BETTER,
            ),
        ),
    )
    preset = TableMappingPreset(
        name="Lab Standard",
        schema_definition=schema,
        created_at=now,
        updated_at=now,
    )

    preset_manager = PresetManager()
    presets_dir = tmp_path / "custom_presets"
    preset_file = preset_manager.save_preset(preset, presets_dir)
    assert preset_file.exists()

    # 2. Ingest two distinct TSV files using the saved preset
    tsv_file = data_dir / "batch_one.tsv"
    tsv_file.write_text("id\tsmiles\tchem_score\nM1\tCCO\t95.0\n", encoding="utf-8")

    loaded_preset = preset_manager.load_preset(preset_file)
    plan = manager.plan(
        "fidelichem.universal_table",
        data_dir,
        options={"schema": loaded_preset.schema_definition.model_dump(mode="json")},
    )

    result = manager.execute_import(project_id, plan)
    assert result.batch.status == ImportStatus.COMPLETED
    assert len(result.confirmed_resolutions) == 1


def test_universal_table_import_skips_chemistry_policy_failures_with_qc(
    table_pipeline_env,
) -> None:
    manager, project_id, data_dir, uow_factory, _ = table_pipeline_env
    source = data_dir / "mixed_identity.csv"
    source.write_text(
        "access_code,smiles\nGOOD,CCO\nAMBIGUOUS,CCO.CN\n",
        encoding="utf-8",
    )
    schema = TableMappingSchema(
        identity=IdentityColumnMapping(
            molecule_id_column="access_code",
            smiles_column="smiles",
            source_system_default="pipeline",
        )
    )
    plan = manager.plan(
        "fidelichem.universal_table",
        source,
        options={"schema": schema.model_dump(mode="json")},
    )

    result = manager.execute_import(project_id, plan)

    assert result.batch.status is ImportStatus.COMPLETED
    assert len(result.confirmed_resolutions) == 1
    assert any(
        "Skipped 1 compounds" in warning
        for warning in result.validation.warnings
    )
    assert any(
        issue.code == "QC_CHEMISTRY_PARENT_MULTIORGANIC"
        for issue in result.validation.qc_issues
    )
    with uow_factory() as uow:
        aliases = uow.aliases.list_by_batch(result.batch.id)
        assert {alias.source_value for alias in aliases} == {"GOOD"}
