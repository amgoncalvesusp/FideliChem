"""Acceptance test for cross-tool identity resolution across pipelines."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from fidelichem.adapters.gold import GoldAdapter
from fidelichem.adapters.registry import AdapterRegistry
from fidelichem.adapters.smiles2docking import Smiles2DockingAdapter
from fidelichem.adapters.smiles2select import Smiles2SelectAdapter
from fidelichem.chemistry.service import ChemistryService
from fidelichem.domain.chemistry import (
    IdentityActor,
)
from fidelichem.domain.models import (
    ActorKind,
    ImportStatus,
    Project,
)
from fidelichem.identity.service import IdentityService
from fidelichem.importers.manager import ImportManager
from fidelichem.storage.engine import create_sqlite_engine
from fidelichem.storage.identity_index import PersistentIdentityIndex
from fidelichem.storage.runner import upgrade_database
from fidelichem.storage.session import UnitOfWork


def test_cross_identity_resolution_pipeline(tmp_path: Path) -> None:
    """Verify SMILES2Select -> SMILES2Docking -> GOLD cross-identity continuity."""
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
    s2s_adapter = Smiles2SelectAdapter()
    s2d_adapter = Smiles2DockingAdapter()
    gold_adapter = GoldAdapter()

    registry.register(s2s_adapter)
    registry.register(s2d_adapter)
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
            Project(name="Cross-Tool Virtual Screening", created_at=now, updated_at=now)
        )

    actor = IdentityActor(kind=ActorKind.USER, actor_id="lead_medicinal_chemist")

    # Step 1: Ingest SMILES2Select filtering dataset
    s2s_dir = tmp_path / "step1_s2s"
    s2s_dir.mkdir()
    (s2s_dir / "smiles2select_results.json").write_text(
        json.dumps(
            [
                {
                    "compound_id": "S2S_LIG_01",
                    "smiles": "CC(=O)Oc1ccccc1C(=O)O",
                    "selected": True,
                    "qed": 0.85,
                    "sa_score": 1.90,
                }
            ]
        ),
        encoding="utf-8",
    )

    plan1 = manager.plan("fidelichem.smiles2select", s2s_dir)
    res1 = manager.execute_import(project.id, plan1, actor=actor)
    assert res1.batch.status == ImportStatus.COMPLETED
    assert len(res1.confirmed_resolutions) == 1
    cmpd_id_s2s = res1.confirmed_resolutions[0].compound_id

    # Step 2: Ingest SMILES2Docking ligand preparation (pH 7.4 state)
    s2d_dir = tmp_path / "step2_s2d"
    s2d_dir.mkdir()
    (s2d_dir / "run.json").write_text(
        json.dumps(
            {
                "run_id": "prep_run_egfr",
                "target_ph": 7.4,
                "protonation_engine": "dimorphite-dl",
                "optimization_method": "PM7",
                "compounds": [
                    {
                        "compound_id": "S2D_LIG_01",
                        "initial_smiles": "CC(=O)Oc1ccccc1C(=O)O",
                        "state_smiles": "CC(=O)Oc1ccccc1C(=O)[O-]",
                        "structure_file": "s2d_lig_01.sdf",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (s2d_dir / "s2d_lig_01.sdf").write_text("$$$$\n", encoding="utf-8")

    plan2 = manager.plan("fidelichem.smiles2docking", s2d_dir)
    res2 = manager.execute_import(project.id, plan2, actor=actor)
    assert res2.batch.status == ImportStatus.COMPLETED
    assert len(res2.confirmed_resolutions) == 1
    cmpd_id_s2d = res2.confirmed_resolutions[0].compound_id

    # Must resolve to the EXACT SAME compound ID
    assert cmpd_id_s2d == cmpd_id_s2s

    # Step 3: Ingest GOLD docking poses referencing the same compound
    gold_dir = tmp_path / "step3_gold"
    gold_dir.mkdir()
    (gold_dir / "gold.conf").write_text(
        "protein_datafile = /structures/egfr_kinase.pdb\nfitness_function = CHEMPLP\n",
        encoding="utf-8",
    )
    (gold_dir / "bestranking.lst").write_text(
        "Rank\tSolution_File\tChemPLP\tLigand_Name\n"
        "1\tgold_soln_s2s_lig_01_m1_1.mol2\t88.40\tS2S_LIG_01\n",
        encoding="utf-8",
    )
    (gold_dir / "gold_soln_s2s_lig_01_m1_1.mol2").write_text(
        "@<TRIPOS>MOLECULE\n"
        "S2S_LIG_01\n"
        " 3 2 0 0 0\n"
        "SMALL\n"
        "NO_CHARGES\n"
        "\n"
        "\n"
        "> <SMILES>\n"
        "CC(=O)Oc1ccccc1C(=O)O\n"
        "> <ChemPLP.Fitness>\n"
        "88.40\n"
        "@<TRIPOS>ATOM\n"
        " 1 C1 0.0 0.0 0.0 C.3 1 LIG 0.0\n"
        " 2 C2 1.5 0.0 0.0 C.3 1 LIG 0.0\n"
        " 3 O1 2.5 1.0 0.0 O.3 1 LIG 0.0\n"
        "@<TRIPOS>BOND\n"
        " 1 1 2 1\n"
        " 2 2 3 1\n",
        encoding="utf-8",
    )

    plan3 = manager.plan("fidelichem.gold", gold_dir)
    res3 = manager.execute_import(project.id, plan3, actor=actor)
    assert res3.batch.status == ImportStatus.COMPLETED
    assert len(res3.confirmed_resolutions) == 1
    cmpd_id_gold = res3.confirmed_resolutions[0].compound_id

    # Cross-evidence resolution verification
    assert cmpd_id_gold == cmpd_id_s2s

    with _uow_factory() as uow:
        # Verify compound in database
        compound = uow.compounds.get(cmpd_id_s2s)
        assert compound is not None
        assert compound.id == cmpd_id_s2s
        assert compound.canonical_smiles == "CC(=O)Oc1ccccc1C(=O)O"

        # Verify molecular state for step 2 (ionized at pH 7.4)
        state_id_s2d = res2.confirmed_resolutions[0].molecular_state_id
        assert state_id_s2d is not None
        state_s2d = uow.molecular_states.get(state_id_s2d)
        assert state_s2d is not None
        assert state_s2d.formal_charge == -1
        assert state_s2d.preparation_ph == 7.4

        # Verify aliases across all 3 batches
        aliases_b1 = uow.aliases.list_by_batch(res1.batch.id)
        assert len(aliases_b1) == 1
        assert aliases_b1[0].source_system == "smiles2select"
        assert aliases_b1[0].source_value == "S2S_LIG_01"

        aliases_b2 = uow.aliases.list_by_batch(res2.batch.id)
        assert len(aliases_b2) == 1
        assert aliases_b2[0].source_system == "smiles2docking"
        assert aliases_b2[0].source_value == "S2D_LIG_01"

        aliases_b3 = uow.aliases.list_by_batch(res3.batch.id)
        assert len(aliases_b3) == 1
        assert aliases_b3[0].source_system == "gold"
        assert aliases_b3[0].source_value == "S2S_LIG_01"

        # 3 import batches
        batches = uow.import_batches.list_by_project(project.id)
        assert len(batches) == 3

    engine.dispose()
