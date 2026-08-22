"""Acceptance test for multi-pose interaction consensus and profiles."""

from __future__ import annotations

from fidelichem.consensus.interaction.consensus import (
    compute_interaction_consensus,
)
from fidelichem.consensus.pose.models import PoseCluster
from fidelichem.domain.adapters import InteractionRecord


def test_interaction_consensus_full_pipeline() -> None:
    """Verify interaction consensus across multi-tool docking and DockLens contacts."""
    # Run 1 (GOLD): Poses P01, P02, P03 (Cluster 1)
    # Run 2 (Vina): Poses P04, P05 (Cluster 2)
    # Target: SARS-CoV-2 Mpro (Active site residues: CYS145, HIS41, GLU166, GLN189)

    interactions = {
        "P01": [
            InteractionRecord(
                run_name="gold_run",
                compound_source_value="NIRMATRELVIR",
                source_pose_id="P01",
                target_name="Mpro",
                residue_name="GLU166",
                interaction_type="hbond",
                distance=2.7,
            ),
            InteractionRecord(
                run_name="gold_run",
                compound_source_value="NIRMATRELVIR",
                source_pose_id="P01",
                target_name="Mpro",
                residue_name="HIS41",
                interaction_type="hbond",
                distance=2.9,
            ),
            InteractionRecord(
                run_name="gold_run",
                compound_source_value="NIRMATRELVIR",
                source_pose_id="P01",
                target_name="Mpro",
                residue_name="CYS145",
                interaction_type="covalent_contact",
                distance=1.8,
            ),
        ],
        "P02": [
            InteractionRecord(
                run_name="gold_run",
                compound_source_value="NIRMATRELVIR",
                source_pose_id="P02",
                target_name="Mpro",
                residue_name="GLU166",
                interaction_type="hbond",
                distance=2.65,
            ),
            InteractionRecord(
                run_name="gold_run",
                compound_source_value="NIRMATRELVIR",
                source_pose_id="P02",
                target_name="Mpro",
                residue_name="HIS41",
                interaction_type="hbond",
                distance=3.0,
            ),
        ],
        "P03": [
            InteractionRecord(
                run_name="gold_run",
                compound_source_value="NIRMATRELVIR",
                source_pose_id="P03",
                target_name="Mpro",
                residue_name="GLU166",
                interaction_type="hbond",
                distance=2.8,
            ),
        ],
        "P04": [
            InteractionRecord(
                run_name="vina_run",
                compound_source_value="NIRMATRELVIR",
                source_pose_id="P04",
                target_name="Mpro",
                residue_name="GLU166",
                interaction_type="hbond",
                distance=2.75,
            ),
            InteractionRecord(
                run_name="vina_run",
                compound_source_value="NIRMATRELVIR",
                source_pose_id="P04",
                target_name="Mpro",
                residue_name="GLN189",
                interaction_type="hbond",
                distance=2.95,
            ),
        ],
        "P05": [
            InteractionRecord(
                run_name="vina_run",
                compound_source_value="NIRMATRELVIR",
                source_pose_id="P05",
                target_name="Mpro",
                residue_name="GLU166",
                interaction_type="hbond",
                distance=2.7,
            ),
            InteractionRecord(
                run_name="vina_run",
                compound_source_value="NIRMATRELVIR",
                source_pose_id="P05",
                target_name="Mpro",
                residue_name="GLN189",
                interaction_type="hbond",
                distance=3.1,
            ),
        ],
    }

    clusters = (
        PoseCluster(
            cluster_id=1,
            medoid_pose_id="P01",
            member_pose_ids=("P01", "P02", "P03"),
            size=3,
        ),
        PoseCluster(
            cluster_id=2,
            medoid_pose_id="P04",
            member_pose_ids=("P04", "P05"),
            size=2,
        ),
    )

    res = compute_interaction_consensus(
        compound_id="NIRMATRELVIR",
        pose_interactions=interactions,
        pose_clusters=clusters,
        conserved_threshold=0.80,
    )

    assert res.total_poses == 5
    assert res.zero_contact_pose_count == 0

    # GLU166 hbond is present in 5/5 poses (100%) -> conserved core
    glu_prev = next(p for p in res.global_prevalences if p.residue_name == "GLU166")
    assert glu_prev.frequency == 1.0
    assert "Mpro|GLU166|hbond" in res.conserved_core_interactions

    # GLN189 hbond is family-specific (0% in cluster 1, 100% in cluster 2)
    f1 = next(f for f in res.family_profiles if f.cluster_id == 1)
    f2 = next(f for f in res.family_profiles if f.cluster_id == 2)
    assert not any(p.residue_name == "GLN189" for p in f1.prevalences)
    assert any(p.residue_name == "GLN189" for p in f2.prevalences)
    assert "Mpro|GLN189|hbond" in f2.conserved_interactions
