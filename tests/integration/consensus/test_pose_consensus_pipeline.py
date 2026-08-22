"""Acceptance integration test for 3D docking pose consensus and clustering."""

from __future__ import annotations

import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from fidelichem.analytics.models import AgreementLevel
from fidelichem.chemistry.service import ChemistryService
from fidelichem.consensus.pose.consensus import compute_pose_consensus


def _build_pose_mol_block(offset_x: float = 0.0, offset_y: float = 0.0) -> str:
    m = Chem.AddHs(Chem.MolFromSmiles("c1ccc(cc1)C(=O)O"))
    AllChem.EmbedMolecule(m, randomSeed=42)
    conf = m.GetConformer()
    for i in range(m.GetNumAtoms()):
        pos = conf.GetAtomPosition(i)
        conf.SetAtomPosition(i, (pos.x + offset_x, pos.y + offset_y, pos.z))
    return Chem.MolToMolBlock(m)


def test_pose_consensus_end_to_end_pipeline() -> None:
    """Verify pose consensus across multi-pose virtual screening results."""
    chem_service = ChemistryService()

    # Create 5 poses:
    # P1, P2, P3, P4 are very close (cluster 1, dominant: 80%)
    # P5 is flipped/shifted by 5.0 A (cluster 2, outlier: 20%)
    p1 = _build_pose_mol_block(offset_x=0.0, offset_y=0.0)
    p2 = _build_pose_mol_block(offset_x=0.2, offset_y=0.1)
    p3 = _build_pose_mol_block(offset_x=-0.2, offset_y=0.1)
    p4 = _build_pose_mol_block(offset_x=0.1, offset_y=-0.2)
    p5 = _build_pose_mol_block(offset_x=5.0, offset_y=5.0)

    pose_dict = {"P01": p1, "P02": p2, "P03": p3, "P04": p4, "P05": p5}

    result = compute_pose_consensus(
        compound_id="CMPD_BENZOIC_DERIVATIVE",
        pose_mol_blocks=pose_dict,
        chemistry_service=chem_service,
        cutoff=2.0,
        align=False,
    )

    assert result.compound_id == "CMPD_BENZOIC_DERIVATIVE"
    assert result.total_poses == 5
    assert len(result.clusters) == 2

    dominant = result.dominant_cluster
    assert dominant is not None
    assert dominant.size == 4
    assert set(dominant.member_pose_ids) == {"P01", "P02", "P03", "P04"}
    assert dominant.mean_rmsd_to_medoid < 0.4

    # 4/5 = 80% dominant cluster yields HIGH consensus level
    assert result.consensus_level == AgreementLevel.HIGH
    assert result.stability_score > 0.65

    # Check RMSD matrix properties
    mat = result.pairwise_rmsd_matrix
    assert mat["P01"]["P01"] == 0.0
    assert pytest.approx(mat["P01"]["P05"], rel=1e-1) == 7.07
    assert mat["P01"]["P02"] == mat["P02"]["P01"]
