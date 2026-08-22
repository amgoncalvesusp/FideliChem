"""Acceptance test for DockLens interaction association with GOLD docking poses."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from fidelichem.adapters.docklens import DockLensAdapter
from fidelichem.adapters.gold import GoldAdapter
from fidelichem.adapters.registry import AdapterRegistry
from fidelichem.chemistry.service import ChemistryService
from fidelichem.domain.chemistry import IdentityActor
from fidelichem.domain.models import ActorKind, ImportStatus, Project
from fidelichem.identity.service import IdentityService
from fidelichem.importers.manager import ImportManager
from fidelichem.storage.engine import create_sqlite_engine
from fidelichem.storage.identity_index import PersistentIdentityIndex
from fidelichem.storage.runner import upgrade_database
from fidelichem.storage.session import UnitOfWork


def test_docklens_gold_pose_association(tmp_path: Path) -> None:
    """Verify GOLD docking pose P003 associates correctly with DockLens interactions."""
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
    docklens_adapter = DockLensAdapter()

    registry.register(gold_adapter)
    registry.register(docklens_adapter)

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
            Project(name="EGFR Mechanistic Profiling", created_at=now, updated_at=now)
        )

    actor = IdentityActor(kind=ActorKind.USER, actor_id="structural_biologist")

    # Step 1: Ingest GOLD docking poses including P003
    gold_dir = tmp_path / "gold_run"
    gold_dir.mkdir()
    (gold_dir / "gold.conf").write_text(
        "protein_datafile = /structures/egfr_kinase.pdb\nfitness_function = CHEMPLP\n",
        encoding="utf-8",
    )
    (gold_dir / "bestranking.lst").write_text(
        "Rank\tSolution_File\tChemPLP\tLigand_Name\n"
        "1\tgold_soln_lig_01_m1_1.mol2\t88.40\tLIG_01\n"
        "2\tgold_soln_lig_01_m1_2.mol2\t82.10\tLIG_01\n"
        "3\tgold_soln_lig_01_m1_3.mol2\t79.50\tLIG_01\n",
        encoding="utf-8",
    )
    for p_idx, fitness in ((1, 88.40), (2, 82.10), (3, 79.50)):
        (gold_dir / f"gold_soln_lig_01_m1_{p_idx}.mol2").write_text(
            "@<TRIPOS>MOLECULE\n"
            f"LIG_01\n"
            " 3 2 0 0 0\n"
            "SMALL\n"
            "NO_CHARGES\n"
            "\n"
            "\n"
            "> <SMILES>\n"
            "CC(=O)Oc1ccccc1C(=O)O\n"
            "> <ChemPLP.Fitness>\n"
            f"{fitness}\n"
            "@<TRIPOS>ATOM\n"
            " 1 C1 0.0 0.0 0.0 C.3 1 LIG 0.0\n"
            " 2 C2 1.5 0.0 0.0 C.3 1 LIG 0.0\n"
            " 3 O1 2.5 1.0 0.0 O.3 1 LIG 0.0\n"
            "@<TRIPOS>BOND\n"
            " 1 1 2 1\n"
            " 2 2 3 1\n",
            encoding="utf-8",
        )

    plan_gold = manager.plan("fidelichem.gold", gold_dir)
    res_gold = manager.execute_import(project.id, plan_gold, actor=actor)
    assert res_gold.batch.status == ImportStatus.COMPLETED
    assert len(res_gold.bundle.poses) == 3
    pose3 = next(p for p in res_gold.bundle.poses if p.rank == 3)
    assert pose3.source_pose_id == "gold_soln_lig_01_m1_3"

    # Step 2: Ingest DockLens mechanistic interactions for Pose 3
    docklens_dir = tmp_path / "docklens_output"
    docklens_dir.mkdir()
    (docklens_dir / "docklens_interactions.json").write_text(
        json.dumps(
            {
                "run_name": res_gold.bundle.docking_runs[0].run_name,
                "target_name": "EGFR",
                "interactions": [
                    {
                        "compound_id": "LIG_01",
                        "pose_id": "gold_soln_lig_01_m1_3",
                        "residue": "MET793",
                        "interaction_type": "hydrogen_bond",
                        "distance": 2.15,
                        "angle": 166.0,
                        "occupancy": 1.0,
                        "ligand_feature": "O1_carboxyl",
                    },
                    {
                        "compound_id": "LIG_01",
                        "pose_id": "gold_soln_lig_01_m1_3",
                        "residue": "LYS745",
                        "interaction_type": "salt_bridge",
                        "distance": 3.40,
                        "occupancy": 0.88,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    plan_dl = manager.plan("fidelichem.docklens", docklens_dir)
    res_dl = manager.execute_import(project.id, plan_dl, actor=actor)
    assert res_dl.batch.status == ImportStatus.COMPLETED
    assert len(res_dl.bundle.interactions) == 2

    # Verify interaction linkage to GOLD Pose 3
    i1, i2 = res_dl.bundle.interactions
    assert i1.source_pose_id == pose3.source_pose_id
    assert i1.run_name == pose3.run_name
    assert i1.compound_source_value == pose3.compound_source_value
    assert i1.interaction_key == "EGFR|MET793|hydrogen_bond"
    assert i1.granular_interaction_key == "EGFR|MET793|hydrogen_bond|O1_carboxyl"

    assert i2.source_pose_id == pose3.source_pose_id
    assert i2.interaction_key == "EGFR|LYS745|salt_bridge"

    engine.dispose()
