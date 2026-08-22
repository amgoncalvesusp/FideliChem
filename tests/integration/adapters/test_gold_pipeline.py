"""Acceptance integration test for GOLD Adapter meeting all Phase 6 criteria."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from fidelichem.adapters.gold import GoldAdapter
from fidelichem.adapters.registry import AdapterRegistry
from fidelichem.chemistry.service import ChemistryService
from fidelichem.domain.chemistry import (
    IdentityActor,
)
from fidelichem.domain.errors import (
    DuplicateImportError,
)
from fidelichem.domain.models import (
    ActorKind,
    ImportStatus,
    Project,
)
from fidelichem.identity.service import IdentityService
from fidelichem.importers.manager import ImportManager
from fidelichem.scoring.normalizer import ScoreNormalizer
from fidelichem.scoring.registry import ScoreRegistry
from fidelichem.storage.engine import create_sqlite_engine
from fidelichem.storage.identity_index import PersistentIdentityIndex
from fidelichem.storage.runner import upgrade_database
from fidelichem.storage.session import UnitOfWork


def _create_gold_run_fixtures(
    run_dir: Path,
    target_name: str,
    fitness_func: str,
    rescore_func: str,
    ligands: tuple[str, str],
) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    conf_file = run_dir / "gold.conf"
    conf_file.write_text(
        f"GOLD CONFIGURATION FILE\n"
        f"protein_datafile = /structures/{target_name}.pdb\n"
        f"fitness_function = {fitness_func}\n"
        f"rescore_function = {rescore_func}\n"
        f"run_name = GOLD_{target_name}_{fitness_func.lower()}\n",
        encoding="utf-8",
    )

    ranking_lines = [
        f"Rank\tSolution_File\t{fitness_func}\t{rescore_func}\tLigand_Name\n"
    ]
    rank_idx = 1
    for lig in ligands:
        for pose_num in range(1, 4):
            soln_filename = f"gold_soln_{lig.lower()}_m1_{pose_num}.mol2"
            score_1 = 90.0 - (rank_idx * 2.5)
            score_2 = 75.0 - (rank_idx * 1.8)
            ranking_lines.append(
                f"{rank_idx}\t{soln_filename}\t{score_1:.2f}\t{score_2:.2f}\t{lig}\n"
            )

            # Create MOL2 file
            mol2_file = run_dir / soln_filename
            smiles_val = (
                "CC(=O)Oc1ccccc1C(=O)O" if "01" in lig else "CC(=O)Nc1ccc(O)cc1"
            )

            mol2_file.write_text(
                f"@<TRIPOS>MOLECULE\n"
                f"{lig}\n"
                f" 3 2 0 0 0\n"
                f"SMALL\n"
                f"NO_CHARGES\n"
                f"\n"
                f"\n"
                f"> <SMILES>\n"
                f"{smiles_val}\n"
                f"> <{fitness_func}.Fitness>\n"
                f"{score_1:.2f}\n"
                f"> <{rescore_func}.Fitness>\n"
                f"{score_2:.2f}\n"
                f"@<TRIPOS>ATOM\n"
                f" 1 C1 0.000 0.000 0.000 C.3 1 <1> 0.0\n"
                f" 2 C2 1.500 0.000 0.000 C.3 1 <1> 0.0\n"
                f" 3 O1 2.500 1.000 0.000 O.3 1 <1> 0.0\n"
                f"@<TRIPOS>BOND\n"
                f" 1 1 2 1\n"
                f" 2 2 3 1\n",
                encoding="utf-8",
            )

            rank_idx += 1

    (run_dir / "bestranking.lst").write_text("".join(ranking_lines), encoding="utf-8")


def test_gold_acceptance_pipeline(tmp_path: Path) -> None:
    # 1. Setup storage
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
    registry = AdapterRegistry()
    gold_adapter = GoldAdapter()
    registry.register(gold_adapter)

    manager = ImportManager(
        registry=registry,
        uow_factory=_uow_factory,
        identity_service=identity_service,
        chemistry_service=chem_service,
        clock=clock,
    )

    now = datetime(2026, 8, 22, 12, 0, 0, tzinfo=UTC)
    with _uow_factory() as uow:
        project = uow.projects.add(
            Project(name="GOLD Multi-Run Campaign", created_at=now, updated_at=now)
        )

    # 2. Create 2 distinct docking runs for 1 target (ctx_m_15),
    # 2 ligands, 3 poses/ligand
    # Run 1: ChemPLP + GoldScore

    run1_dir = tmp_path / "run1_chemplp"
    _create_gold_run_fixtures(
        run1_dir,
        target_name="ctx_m_15",
        fitness_func="CHEMPLP",
        rescore_func="GOLDSCORE",
        ligands=("CTX_LIG_01", "CTX_LIG_02"),
    )

    # Run 2: ASP + ChemScore
    run2_dir = tmp_path / "run2_asp"
    _create_gold_run_fixtures(
        run2_dir,
        target_name="ctx_m_15",
        fitness_func="ASP",
        rescore_func="CHEMSCORE",
        ligands=("CTX_LIG_01", "CTX_LIG_02"),
    )

    # 3. Plan & parse both runs
    plan1 = manager.plan("fidelichem.gold", run1_dir)
    bundle1 = gold_adapter.parse(plan1)

    assert len(bundle1.targets) == 1
    assert bundle1.targets[0].name == "ctx_m_15"
    assert len(bundle1.docking_runs) == 1
    assert bundle1.docking_runs[0].engine == "GOLD"
    assert len(bundle1.compounds) == 2
    assert len(bundle1.poses) == 6  # 2 ligands * 3 poses
    # 6 poses * 2 score types (ChemPLP + GoldScore) = 12 observations
    assert len(bundle1.scores) == 12
    score_keys1 = {s.score_key for s in bundle1.scores}
    assert score_keys1 == {"gold.chemplp", "gold.goldscore"}

    plan2 = manager.plan("fidelichem.gold", run2_dir)
    bundle2 = gold_adapter.parse(plan2)
    assert len(bundle2.poses) == 6
    assert len(bundle2.scores) == 12
    score_keys2 = {s.score_key for s in bundle2.scores}
    assert score_keys2 == {"gold.asp", "gold.chemscore"}

    # 4. Ingest Run 1 into Database
    actor = IdentityActor(kind=ActorKind.USER, actor_id="docking_expert")
    res1 = manager.execute_import(project.id, plan1, actor=actor)
    assert res1.batch.status == ImportStatus.COMPLETED
    assert len(res1.confirmed_resolutions) == 2

    # Ingest Run 2 into Database
    res2 = manager.execute_import(project.id, plan2, actor=actor)
    assert res2.batch.status == ImportStatus.COMPLETED
    assert len(res2.confirmed_resolutions) == 2

    # 5. Verify database records
    with _uow_factory() as uow:
        batches = uow.import_batches.list_by_project(project.id)
        assert len(batches) == 2

        # Verify aliases
        aliases1 = uow.aliases.list_by_batch(res1.batch.id)
        assert len(aliases1) == 2
        aliases2 = uow.aliases.list_by_batch(res2.batch.id)
        assert len(aliases2) == 2

        # Verify artifacts
        artifacts1 = uow.source_artifacts.list_by_batch(res1.batch.id)
        assert len(artifacts1) >= 7  # gold.conf + bestranking.lst + 6 mol2

    # 6. Verify Normalization on GOLD Scores
    score_registry = ScoreRegistry.create_default()
    normalizer = ScoreNormalizer()

    # ChemPLP normalization
    plp_entries = [
        {"raw": s.raw_value, "entity": s.source_pose_id}
        for s in bundle1.scores
        if s.score_key == "gold.chemplp"
    ]
    norm_plp, plp_stats = normalizer.normalize_values(
        plp_entries,
        definition=score_registry.get("gold.chemplp"),
        scope_key="ctx_m_15/GOLD_ctx_m_15_chemplp",
        value_key="raw",
        entity_key="entity",
    )
    assert plp_stats.count_observed == 6
    assert norm_plp[0].rank == 1
    assert norm_plp[0].percentile == 1.0

    # 7. Duplicate import rejection
    with pytest.raises(DuplicateImportError, match="Duplicate import detected"):
        manager.execute_import(project.id, plan1, actor=actor)

    # 8. Rollback and re-import
    rolled = manager.rollback_import(
        project.id,
        res1.batch.id,
        reason="Re-dock with updated cavity",
        actor=actor,
    )
    assert rolled.status == ImportStatus.ROLLED_BACK

    reimport_res = manager.execute_import(project.id, plan1, actor=actor)
    assert reimport_res.batch.status == ImportStatus.COMPLETED

    engine.dispose()
