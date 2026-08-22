"""Unit tests for interaction consensus and contact prevalence."""

from __future__ import annotations

import pytest

from fidelichem.consensus.interaction.consensus import (
    compute_interaction_consensus,
)
from fidelichem.consensus.pose.models import PoseCluster
from fidelichem.domain.adapters import InteractionRecord


def test_interaction_consensus_prevalence_and_zero_contact() -> None:
    # 5 poses:
    # P1, P2, P3, P4 have H-bond with MET793
    # P1, P2 have pi-stacking with PHE723
    # P5 has ZERO contacts (empty list)
    int_p1 = [
        InteractionRecord(
            run_name="dock_run",
            compound_source_value="ERLOTINIB",
            source_pose_id="P1",
            residue_name="MET793",
            interaction_type="hbond",
            distance=2.8,
        ),
        InteractionRecord(
            run_name="dock_run",
            compound_source_value="ERLOTINIB",
            source_pose_id="P1",
            residue_name="MET793",
            interaction_type="hbond",
            distance=2.9,
        ),  # duplicate atom-pair contact in same pose
        InteractionRecord(
            run_name="dock_run",
            compound_source_value="ERLOTINIB",
            source_pose_id="P1",
            residue_name="PHE723",
            interaction_type="pi_stacking",
            distance=3.6,
        ),
    ]
    int_p2 = [
        InteractionRecord(
            run_name="dock_run",
            compound_source_value="ERLOTINIB",
            source_pose_id="P2",
            residue_name="MET793",
            interaction_type="hbond",
            distance=2.7,
        ),
        InteractionRecord(
            run_name="dock_run",
            compound_source_value="ERLOTINIB",
            source_pose_id="P2",
            residue_name="PHE723",
            interaction_type="pi_stacking",
            distance=3.8,
        ),
    ]
    int_p3 = [
        InteractionRecord(
            run_name="dock_run",
            compound_source_value="ERLOTINIB",
            source_pose_id="P3",
            residue_name="MET793",
            interaction_type="hbond",
            distance=2.85,
        ),
    ]
    int_p4 = [
        InteractionRecord(
            run_name="dock_run",
            compound_source_value="ERLOTINIB",
            source_pose_id="P4",
            residue_name="MET793",
            interaction_type="hbond",
            distance=3.0,
        ),
    ]
    int_p5: list[InteractionRecord] = []

    pose_dict = {
        "P1": int_p1,
        "P2": int_p2,
        "P3": int_p3,
        "P4": int_p4,
        "P5": int_p5,
    }

    res = compute_interaction_consensus(
        compound_id="CMPD_ERLOTINIB",
        pose_interactions=pose_dict,
        conserved_threshold=0.75,
    )

    assert res.total_poses == 5
    assert res.zero_contact_pose_count == 1

    # MET793 hbond observed in P1, P2, P3, P4 (4/5 = 80%)
    hbond_prev = next(p for p in res.global_prevalences if p.residue_name == "MET793")
    assert hbond_prev.observed_count == 4
    assert hbond_prev.total_poses == 5
    assert pytest.approx(hbond_prev.frequency, rel=1e-2) == 0.80
    assert hbond_prev.mean_distance is not None
    assert hbond_prev.mean_distance < 2.9

    # PHE723 pi_stacking observed in P1, P2 (2/5 = 40%)
    pi_prev = next(p for p in res.global_prevalences if p.residue_name == "PHE723")
    assert pi_prev.observed_count == 2
    assert pytest.approx(pi_prev.frequency, rel=1e-2) == 0.40

    # Conserved core interactions (threshold >= 0.75) includes MET793, excludes PHE723
    assert len(res.conserved_core_interactions) == 1
    assert "MET793" in res.conserved_core_interactions[0]

    # Residue matrix
    assert res.residue_interaction_matrix["MET793"]["hbond"] == 0.80
    assert res.residue_interaction_matrix["PHE723"]["pi_stacking"] == 0.40


def test_interaction_consensus_with_pose_families() -> None:
    # Cluster 1: {P1, P2, P3}
    # Cluster 2: {P4, P5}
    int_p1 = [
        InteractionRecord(
            run_name="r1",
            compound_source_value="c1",
            source_pose_id="P1",
            residue_name="ASP855",
            interaction_type="salt_bridge",
        )
    ]
    int_p2 = [
        InteractionRecord(
            run_name="r1",
            compound_source_value="c1",
            source_pose_id="P2",
            residue_name="ASP855",
            interaction_type="salt_bridge",
        )
    ]
    int_p3 = [
        InteractionRecord(
            run_name="r1",
            compound_source_value="c1",
            source_pose_id="P3",
            residue_name="ASP855",
            interaction_type="salt_bridge",
        )
    ]
    int_p4 = [
        InteractionRecord(
            run_name="r1",
            compound_source_value="c1",
            source_pose_id="P4",
            residue_name="THR854",
            interaction_type="hbond",
        )
    ]
    int_p5 = [
        InteractionRecord(
            run_name="r1",
            compound_source_value="c1",
            source_pose_id="P5",
            residue_name="THR854",
            interaction_type="hbond",
        )
    ]

    pose_dict = {
        "P1": int_p1,
        "P2": int_p2,
        "P3": int_p3,
        "P4": int_p4,
        "P5": int_p5,
    }

    c1 = PoseCluster(
        cluster_id=1,
        medoid_pose_id="P1",
        member_pose_ids=("P1", "P2", "P3"),
        size=3,
    )
    c2 = PoseCluster(
        cluster_id=2,
        medoid_pose_id="P4",
        member_pose_ids=("P4", "P5"),
        size=2,
    )

    res = compute_interaction_consensus(
        compound_id="CMPD_KINASE",
        pose_interactions=pose_dict,
        pose_clusters=(c1, c2),
        conserved_threshold=0.80,
    )

    assert len(res.family_profiles) == 2
    f1 = res.family_profiles[0]
    assert f1.cluster_id == 1
    assert f1.member_pose_count == 3
    assert len(f1.conserved_interactions) == 1
    assert "ASP855" in f1.conserved_interactions[0]

    f2 = res.family_profiles[1]
    assert f2.cluster_id == 2
    assert f2.member_pose_count == 2
    assert len(f2.conserved_interactions) == 1
    assert "THR854" in f2.conserved_interactions[0]
