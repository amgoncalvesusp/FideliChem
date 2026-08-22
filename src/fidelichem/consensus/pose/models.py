"""Domain models for structural pose clustering and conformer consensus."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import Field

from fidelichem.analytics.models import AgreementLevel
from fidelichem.domain.models import DomainModel


class PoseCluster(DomainModel):
    """Cluster of structurally similar 3D binding poses."""

    cluster_id: int
    medoid_pose_id: str
    member_pose_ids: tuple[str, ...]
    mean_rmsd_to_medoid: float = 0.0
    max_rmsd_to_medoid: float = 0.0
    size: int = Field(ge=1, strict=True)


class PoseConsensusResult(DomainModel):
    """Aggregate structural consensus analysis across multi-tool or multi-run poses."""

    compound_id: str
    clusters: tuple[PoseCluster, ...]
    pairwise_rmsd_matrix: Mapping[str, Mapping[str, float]]
    consensus_level: AgreementLevel = AgreementLevel.UNKNOWN
    dominant_cluster: PoseCluster | None = None
    stability_score: float = Field(ge=0.0, le=1.0, default=0.0)
    total_poses: int = Field(ge=0, strict=True)
    metadata: Mapping[str, Any] = Field(default_factory=dict)


__all__ = ["PoseCluster", "PoseConsensusResult"]
