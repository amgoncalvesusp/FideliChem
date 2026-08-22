"""Unit tests for pose clustering, medoid selection, and consensus evaluation."""

from __future__ import annotations

from fidelichem.analytics.models import AgreementLevel
from fidelichem.chemistry.service import ChemistryService
from fidelichem.consensus.pose.clustering import cluster_poses
from fidelichem.consensus.pose.consensus import compute_pose_consensus


def test_cluster_poses_distinct_groups() -> None:
    # 2 clear clusters: {P1, P2, P3} within ~0.5 A, and {P4, P5} within ~0.4 A
    matrix = {
        "P1": {"P1": 0.0, "P2": 0.5, "P3": 0.6, "P4": 4.0, "P5": 4.2},
        "P2": {"P1": 0.5, "P2": 0.0, "P3": 0.4, "P4": 4.1, "P5": 4.3},
        "P3": {"P1": 0.6, "P2": 0.4, "P3": 0.0, "P4": 4.2, "P5": 4.4},
        "P4": {"P1": 4.0, "P2": 4.1, "P3": 4.2, "P4": 0.0, "P5": 0.4},
        "P5": {"P1": 4.2, "P2": 4.3, "P3": 4.4, "P4": 0.4, "P5": 0.0},
    }

    clusters = cluster_poses(matrix, cutoff=1.5)
    assert len(clusters) == 2

    c1 = clusters[0]
    assert c1.size == 3
    assert set(c1.member_pose_ids) == {"P1", "P2", "P3"}
    assert c1.medoid_pose_id == "P2"
    assert c1.mean_rmsd_to_medoid < 0.5

    c2 = clusters[1]
    assert c2.size == 2
    assert set(c2.member_pose_ids) == {"P4", "P5"}


def test_cluster_single_pose() -> None:
    matrix = {"P1": {"P1": 0.0}}
    clusters = cluster_poses(matrix, cutoff=2.0)
    assert len(clusters) == 1
    assert clusters[0].medoid_pose_id == "P1"
    assert clusters[0].size == 1
    assert clusters[0].mean_rmsd_to_medoid == 0.0


def test_compute_pose_consensus_empty_and_levels() -> None:
    chem = ChemistryService()
    res_empty = compute_pose_consensus("CMPD_EMPTY", {}, chem)
    assert res_empty.total_poses == 0
    assert res_empty.consensus_level == AgreementLevel.UNKNOWN
    assert res_empty.dominant_cluster is None
