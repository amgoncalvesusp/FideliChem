"""High-level pose consensus calculation across multiple docking solutions."""

from __future__ import annotations

from collections.abc import Mapping

from fidelichem.analytics.models import AgreementLevel
from fidelichem.chemistry.service import ChemistryService

from .clustering import cluster_poses
from .models import PoseConsensusResult


def compute_pose_consensus(
    compound_id: str,
    pose_mol_blocks: Mapping[str, str],
    chemistry_service: ChemistryService,
    cutoff: float = 2.0,
    align: bool = False,
) -> PoseConsensusResult:
    """Evaluate structural pose consensus and determine dominant binding modes."""
    total_poses = len(pose_mol_blocks)
    if total_poses == 0:
        return PoseConsensusResult(
            compound_id=compound_id,
            clusters=(),
            pairwise_rmsd_matrix={},
            consensus_level=AgreementLevel.UNKNOWN,
            dominant_cluster=None,
            stability_score=0.0,
            total_poses=0,
        )

    matrix = chemistry_service.calculate_pose_rmsd_matrix(pose_mol_blocks, align=align)
    clusters = cluster_poses(matrix, cutoff=cutoff)

    dominant = clusters[0] if clusters else None
    if dominant is not None and total_poses > 0:
        dominant_fraction = dominant.size / total_poses
        if dominant_fraction >= 0.70:
            level = AgreementLevel.HIGH
        elif dominant_fraction >= 0.40:
            level = AgreementLevel.MODERATE
        else:
            level = AgreementLevel.LOW

        mean_err = dominant.mean_rmsd_to_medoid
        tightness = max(0.0, 1.0 - (mean_err / cutoff)) if cutoff > 0 else 1.0
        stability = min(1.0, max(0.0, dominant_fraction * tightness))
    else:
        level = AgreementLevel.UNKNOWN
        stability = 0.0

    return PoseConsensusResult(
        compound_id=compound_id,
        clusters=clusters,
        pairwise_rmsd_matrix=matrix,
        consensus_level=level,
        dominant_cluster=dominant,
        stability_score=stability,
        total_poses=total_poses,
        metadata={"cutoff": cutoff, "align": align},
    )


__all__ = ["compute_pose_consensus"]
