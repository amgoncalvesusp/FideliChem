"""Integration tests for ScoreRegistry and NormalizationEngine."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fidelichem.adapters.registry import AdapterRegistry
from fidelichem.adapters.table import UniversalTableAdapter
from fidelichem.chemistry.service import ChemistryService
from fidelichem.domain.chemistry import (
    IdentityActor,
)
from fidelichem.domain.models import (
    ActorKind,
    Project,
)
from fidelichem.domain.scoring import (
    ScoreDirection,
)
from fidelichem.domain.table_importer import (
    IdentityColumnMapping,
    ScoreColumnMapping,
    TableMappingSchema,
)
from fidelichem.identity.service import IdentityService
from fidelichem.importers.manager import ImportManager
from fidelichem.scoring.normalizer import ScoreNormalizer
from fidelichem.scoring.registry import ScoreRegistry
from fidelichem.storage.engine import create_sqlite_engine
from fidelichem.storage.identity_index import PersistentIdentityIndex
from fidelichem.storage.runner import upgrade_database
from fidelichem.storage.session import UnitOfWork


def test_scoring_pipeline_multi_method_normalization(tmp_path: Path) -> None:
    # 1. Setup project and storage
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
    chem_service = ChemistryService()
    adapter_registry = AdapterRegistry()
    table_adapter = UniversalTableAdapter()
    adapter_registry.register(table_adapter)

    manager = ImportManager(
        registry=adapter_registry,
        uow_factory=_uow_factory,
        identity_service=identity_service,
        chemistry_service=chem_service,
        clock=clock,
    )

    now = datetime(2026, 8, 22, 12, 0, 0, tzinfo=UTC)
    with _uow_factory() as uow:
        project = uow.projects.add(
            Project(name="Scoring Integration Campaign", created_at=now, updated_at=now)
        )

    # 2. Create multi-method CSV
    # (ChemPLP higher is better, Vina affinity lower is better)
    data_dir = tmp_path / "data"

    data_dir.mkdir()
    csv_file = data_dir / "docking_campaign.csv"
    csv_file.write_text(
        "Compound_ID,SMILES,Target,Run_ID,ChemPLP,Vina_Affinity\n"
        "MOL_01,CC(=O)Oc1ccccc1C(=O)O,EGFR,Run_A,92.4,-10.5\n"
        "MOL_02,CC(=O)Nc1ccc(O)cc1,EGFR,Run_A,75.0,-8.2\n"
        "MOL_03,c1ccccc1,EGFR,Run_A,50.0,-6.1\n"
        "MOL_04,CCN,EGFR,Run_A,30.0,\n"  # Missing Vina score
        "MOL_05,CCO,EGFR,Run_A,, -4.0\n",  # Missing ChemPLP score
        encoding="utf-8",
    )

    schema = TableMappingSchema(
        identity=IdentityColumnMapping(
            molecule_id_column="Compound_ID",
            smiles_column="SMILES",
            target_name_column="Target",
            run_name_column="Run_ID",
            source_system_default="in_house",
        ),
        scores=(
            ScoreColumnMapping(
                column_name="ChemPLP",
                score_key="gold.chemplp",
                direction=ScoreDirection.HIGHER_BETTER,
            ),
            ScoreColumnMapping(
                column_name="Vina_Affinity",
                score_key="vina.affinity",
                direction=ScoreDirection.LOWER_BETTER,
            ),
        ),
    )

    # 3. Plan & parse bundle
    plan = manager.plan(
        "fidelichem.universal_table",
        data_dir,
        options={"schema": schema.model_dump(mode="json")},
    )

    bundle = table_adapter.parse(plan)
    assert len(bundle.compounds) == 5
    # Total scores: 4 ChemPLP + 4 Vina = 8 score observations
    assert len(bundle.scores) == 8

    # 4. Score Normalization Pipeline
    score_registry = ScoreRegistry.create_default()
    normalizer = ScoreNormalizer()

    # Normalize ChemPLP (higher is better)
    chemplp_defn = score_registry.get("gold.chemplp")
    chemplp_obs = [
        {"raw_value": s.raw_value, "entity": s.compound_source_value}
        for s in bundle.scores
        if s.score_key == "gold.chemplp"
    ]
    norm_plp, plp_stats = normalizer.normalize_values(
        chemplp_obs,
        definition=chemplp_defn,
        scope_key="EGFR/Run_A",
        value_key="raw_value",
        entity_key="entity",
    )

    assert plp_stats.count_observed == 4
    assert plp_stats.min_raw == 30.0
    assert plp_stats.max_raw == 92.4

    # MOL_01 (92.4) is top rank 1, percentile 1.0
    top_plp = next(p for p in norm_plp if p.entity_reference == "MOL_01")
    assert top_plp.rank == 1
    assert top_plp.percentile == 1.0
    assert top_plp.raw_value == 92.4

    # Normalize Vina (lower is better: -10.5 is best)
    vina_defn = score_registry.get("vina.affinity")
    vina_obs = [
        {"raw_value": s.raw_value, "entity": s.compound_source_value}
        for s in bundle.scores
        if s.score_key == "vina.affinity"
    ]
    norm_vina, vina_stats = normalizer.normalize_values(
        vina_obs,
        definition=vina_defn,
        scope_key="EGFR/Run_A",
        value_key="raw_value",
        entity_key="entity",
    )

    assert vina_stats.count_observed == 4
    assert vina_stats.min_raw == -10.5
    assert vina_stats.max_raw == -4.0

    # MOL_01 (-10.5) is top rank 1, percentile 1.0
    top_vina = next(v for v in norm_vina if v.entity_reference == "MOL_01")
    assert top_vina.rank == 1
    assert top_vina.percentile == 1.0
    assert top_vina.raw_value == -10.5

    # 5. Ingest into database via ImportManager
    actor = IdentityActor(kind=ActorKind.USER, actor_id="analyst_1")
    res = manager.execute_import(project.id, plan, actor=actor)
    assert len(res.confirmed_resolutions) == 5

    engine.dispose()
