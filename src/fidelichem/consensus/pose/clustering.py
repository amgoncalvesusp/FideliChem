"""Cutoff-based pose clustering and exact medoid centroid extraction."""

from __future__ import annotations

import statistics
from collections.abc import Mapping

from .models import PoseCluster


def cluster_poses(
    pairwise_rmsd: Mapping[str, Mapping[str, float]],
    cutoff: float = 2.0,
) -> tuple[PoseCluster, ...]:
    """Cluster poses using leader-follower / Butina algorithm with medoids.

    Medoid is the candidate within the cluster minimizing the mean RMSD to
    all other members of the same cluster.
    """

    pose_keys = list(pairwise_rmsd.keys())
    if not pose_keys:
        return ()

    # Precalculate neighbor sets within cutoff
    neighbors: dict[str, set[str]] = {}
    for p1 in pose_keys:
        n_set: set[str] = set()
        for p2 in pose_keys:
            dist = pairwise_rmsd.get(p1, {}).get(p2)
            if dist is not None and dist <= cutoff:
                n_set.add(p2)
        neighbors[p1] = n_set

    unassigned = set(pose_keys)
    raw_clusters: list[list[str]] = []

    while unassigned:
        # Pick candidate with maximum remaining unassigned neighbors
        best_candidate = max(
            unassigned,
            key=lambda p: (
                len(neighbors[p] & unassigned),
                p,
            ),
        )
        cluster_members = list(neighbors[best_candidate] & unassigned)
        if not cluster_members:
            cluster_members = [best_candidate]

        raw_clusters.append(cluster_members)
        unassigned.difference_update(cluster_members)

    # Sort clusters descending by size
    raw_clusters.sort(key=lambda c: len(c), reverse=True)

    result_clusters: list[PoseCluster] = []
    for cluster_idx, members in enumerate(raw_clusters, start=1):
        if len(members) == 1:
            medoid = members[0]
            mean_dist = 0.0
            max_dist = 0.0
        else:
            # Determine medoid minimizing average distance
            best_medoid = members[0]
            min_avg_dist = float("inf")
            for cand in members:
                dists = [
                    pairwise_rmsd.get(cand, {}).get(other, 0.0)
                    for other in members
                    if other != cand
                ]
                avg_d = statistics.mean(dists) if dists else 0.0
                if avg_d < min_avg_dist:
                    min_avg_dist = avg_d
                    best_medoid = cand

            medoid = best_medoid
            dists_to_medoid = [
                pairwise_rmsd.get(medoid, {}).get(other, 0.0) for other in members
            ]
            mean_dist = statistics.mean(dists_to_medoid)
            max_dist = max(dists_to_medoid)

        result_clusters.append(
            PoseCluster(
                cluster_id=cluster_idx,
                medoid_pose_id=medoid,
                member_pose_ids=tuple(sorted(members)),
                mean_rmsd_to_medoid=mean_dist,
                max_rmsd_to_medoid=max_dist,
                size=len(members),
            )
        )

    return tuple(result_clusters)


__all__ = ["cluster_poses"]
