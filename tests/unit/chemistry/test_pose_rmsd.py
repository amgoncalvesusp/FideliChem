"""Unit tests for symmetry-aware 3D pose RMSD calculation."""

from __future__ import annotations

import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from fidelichem.chemistry.service import ChemistryService


def _generate_benzene_mol_block(offset_x: float = 0.0) -> str:
    m = Chem.AddHs(Chem.MolFromSmiles("c1ccccc1"))
    AllChem.EmbedMolecule(m, randomSeed=42)
    conf = m.GetConformer()
    if offset_x != 0.0:
        for i in range(m.GetNumAtoms()):
            pos = conf.GetAtomPosition(i)
            conf.SetAtomPosition(i, (pos.x + offset_x, pos.y, pos.z))
    return Chem.MolToMolBlock(m)


def test_identical_pose_rmsd() -> None:
    service = ChemistryService()
    block = _generate_benzene_mol_block()
    rmsd = service.calculate_pose_rmsd(block, block)
    assert pytest.approx(rmsd, abs=1e-5) == 0.0


def test_translated_pose_rmsd() -> None:
    service = ChemistryService()
    b1 = _generate_benzene_mol_block(offset_x=0.0)
    b2 = _generate_benzene_mol_block(offset_x=2.0)

    # In-pocket translation produces 2.0 A RMSD
    rmsd_unaligned = service.calculate_pose_rmsd(b1, b2, align=False)
    assert pytest.approx(rmsd_unaligned, rel=1e-2) == 2.0

    # Rigid-body alignment superimposes them back to 0.0 A RMSD
    rmsd_aligned = service.calculate_pose_rmsd(b1, b2, align=True)
    assert pytest.approx(rmsd_aligned, abs=1e-4) == 0.0


def test_pose_rmsd_matrix() -> None:
    service = ChemistryService()
    b1 = _generate_benzene_mol_block(offset_x=0.0)
    b2 = _generate_benzene_mol_block(offset_x=1.0)
    b3 = _generate_benzene_mol_block(offset_x=2.0)

    poses = {"P1": b1, "P2": b2, "P3": b3}
    matrix = service.calculate_pose_rmsd_matrix(poses, align=False)

    assert set(matrix.keys()) == {"P1", "P2", "P3"}
    assert matrix["P1"]["P1"] == 0.0
    assert pytest.approx(matrix["P1"]["P2"], rel=1e-2) == 1.0
    assert pytest.approx(matrix["P1"]["P3"], rel=1e-2) == 2.0
    assert matrix["P1"]["P2"] == matrix["P2"]["P1"]
