"""Acceptance test for GROMACS and MolDynStudio molecular dynamics evidence import."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from fidelichem.adapters.gromacs import GromacsAdapter
from fidelichem.adapters.moldynstudio import MolDynStudioAdapter
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


def test_molecular_dynamics_pipeline_integration(tmp_path: Path) -> None:
    """Verify GROMACS XVG and MolDynStudio simulation ingestion pipelines."""
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
    gromacs_adapter = GromacsAdapter()
    moldyn_adapter = MolDynStudioAdapter()

    registry.register(gromacs_adapter)
    registry.register(moldyn_adapter)

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
            Project(name="EGFR MD Simulations", created_at=now, updated_at=now)
        )

    actor = IdentityActor(kind=ActorKind.USER, actor_id="computational_biophysicist")

    # Step 1: Import GROMACS XVG analytical curves
    gmx_dir = tmp_path / "gromacs_run"
    gmx_dir.mkdir()
    (gmx_dir / "rmsd_backbone.xvg").write_text(
        """# GROMACS RMSD Backbone
@ title "RMSD Protein Backbone"
@ xaxis label "Time (ns)"
@ yaxis label "RMSD (nm)"
@ s0 legend "Backbone"
  0.000 0.045
 10.000 0.145
 20.000 0.178
 30.000 0.185
""",
        encoding="utf-8",
    )
    (gmx_dir / "sasa.xvg").write_text(
        """# GROMACS SASA
@ title "Solvent Accessible Surface Area"
@ xaxis label "Time (ns)"
@ yaxis label "SASA (nm^2)"
@ s0 legend "Total SASA"
  0.000 185.5
 10.000 182.3
 20.000 180.1
 30.000 181.4
""",
        encoding="utf-8",
    )

    plan_gmx = manager.plan("fidelichem.gromacs", gmx_dir)
    res_gmx = manager.execute_import(project.id, plan_gmx, actor=actor)
    assert res_gmx.batch.status == ImportStatus.COMPLETED
    assert len(res_gmx.bundle.md_metrics) == 2
    assert len(res_gmx.bundle.md_runs) == 1

    # Step 2: Import MolDynStudio simulation report
    md_dir = tmp_path / "moldynstudio_run"
    md_dir.mkdir()
    (md_dir / "fidelichem-md-result-v1.json").write_text(
        json.dumps(
            {
                "run_name": "md_prod_100ns_egfr",
                "target_name": "EGFR",
                "compound_id": "LIG_ERLOTINIB",
                "pose_id": "P001",
                "duration_ns": 100.0,
                "temperature_k": 310.15,
                "timestep_fs": 2.0,
                "metrics": [
                    {
                        "metric_key": "rmsd_ligand",
                        "mean": 0.14,
                        "std": 0.025,
                        "min": 0.05,
                        "max": 0.19,
                        "unit": "nm",
                    },
                    {
                        "metric_key": "hbond_occupancy_met793",
                        "mean": 0.94,
                        "std": 0.05,
                        "unit": "fraction",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    plan_md = manager.plan("fidelichem.moldynstudio", md_dir)
    res_md = manager.execute_import(project.id, plan_md, actor=actor)
    assert res_md.batch.status == ImportStatus.COMPLETED
    assert len(res_md.bundle.md_runs) == 1
    assert len(res_md.bundle.md_metrics) == 2

    run = res_md.bundle.md_runs[0]
    assert run.run_name == "md_prod_100ns_egfr"
    assert run.duration_ns == 100.0
    assert run.target_name == "EGFR"
    assert run.compound_source_value == "LIG_ERLOTINIB"

    with _uow_factory() as uow:
        batches = uow.import_batches.list_by_project(project.id)
        assert len(batches) == 2

    engine.dispose()
