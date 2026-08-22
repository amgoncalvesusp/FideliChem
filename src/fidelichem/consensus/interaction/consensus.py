"""Intermolecular interaction consensus engine and contact prevalence analytics."""

from __future__ import annotations

import statistics
from collections.abc import Mapping, Sequence
from typing import Literal

from fidelichem.consensus.pose.models import PoseCluster
from fidelichem.domain.adapters import InteractionRecord

from .models import (
    InteractionConsensusResult,
    InteractionPrevalence,
    PoseFamilyInteractionProfile,
)


def _compute_prevalences_for_subset(
    subset_interactions: Mapping[str, Sequence[InteractionRecord]],
    key_mode: Literal["standard", "granular"] = "standard",
) -> tuple[InteractionPrevalence, ...]:
    """Compute interaction prevalence metrics for a specified subset of poses."""
    total_poses = len(subset_interactions)
    if total_poses == 0:
        return ()

    # Group contacts by interaction key
    key_pose_hits: dict[str, set[str]] = {}
    key_distances: dict[str, list[float]] = {}
    key_angles: dict[str, list[float]] = {}
    key_metadata: dict[str, tuple[str, str, str]] = {}

    for pose_id, records in subset_interactions.items():
        for r in records:
            k = (
                r.granular_interaction_key
                if key_mode == "granular"
                else r.interaction_key
            )

            if k not in key_pose_hits:
                key_pose_hits[k] = set()
                key_distances[k] = []
                key_angles[k] = []
                key_metadata[k] = (
                    r.target_name or "target",
                    r.residue_name,
                    r.interaction_type,
                )

            key_pose_hits[k].add(pose_id)
            if r.distance is not None:
                key_distances[k].append(r.distance)
            if r.angle is not None:
                key_angles[k].append(r.angle)

    prevalences: list[InteractionPrevalence] = []
    for k, hit_set in key_pose_hits.items():
        obs_count = len(hit_set)
        freq = obs_count / total_poses
        tgt, res, itype = key_metadata[k]

        dists = key_distances[k]
        angles = key_angles[k]

        mean_dist = statistics.mean(dists) if dists else None
        min_dist = min(dists) if dists else None
        mean_ang = statistics.mean(angles) if angles else None

        prevalences.append(
            InteractionPrevalence(
                interaction_key=k,
                target_name=tgt,
                residue_name=res,
                interaction_type=itype,
                observed_count=obs_count,
                total_poses=total_poses,
                frequency=freq,
                mean_distance=mean_dist,
                min_distance=min_dist,
                mean_angle=mean_ang,
            )
        )

    # Sort descending by frequency
    prevalences.sort(key=lambda p: (-p.frequency, p.interaction_key))
    return tuple(prevalences)


def compute_interaction_consensus(
    compound_id: str,
    pose_interactions: Mapping[str, Sequence[InteractionRecord]],
    pose_clusters: Sequence[PoseCluster] | None = None,
    key_mode: Literal["standard", "granular"] = "standard",
    conserved_threshold: float = 0.75,
) -> InteractionConsensusResult:
    """Compute contact prevalence, residue interaction matrix, and pose family profiles.

    Missing contacts and zero-contact poses are fully preserved in denominators.
    """
    total_poses = len(pose_interactions)
    if total_poses == 0:
        return InteractionConsensusResult(
            compound_id=compound_id,
            global_prevalences=(),
            family_profiles=(),
            residue_interaction_matrix={},
            conserved_core_interactions=(),
            total_poses=0,
            zero_contact_pose_count=0,
        )

    zero_contact_count = sum(1 for records in pose_interactions.values() if not records)

    # 1. Global prevalences across all poses
    global_prevs = _compute_prevalences_for_subset(pose_interactions, key_mode=key_mode)

    # 2. Build residue -> interaction_type -> frequency matrix
    res_matrix: dict[str, dict[str, float]] = {}
    for p in global_prevs:
        if p.residue_name not in res_matrix:
            res_matrix[p.residue_name] = {}
        res_matrix[p.residue_name][p.interaction_type] = p.frequency

    # 3. Conserved core interactions
    conserved_core = tuple(
        p.interaction_key for p in global_prevs if p.frequency >= conserved_threshold
    )

    # 4. Pose family profiles
    family_profiles: list[PoseFamilyInteractionProfile] = []
    if pose_clusters:
        for cl in pose_clusters:
            sub_dict = {
                pid: pose_interactions.get(pid, ()) for pid in cl.member_pose_ids
            }
            cl_prevs = _compute_prevalences_for_subset(sub_dict, key_mode=key_mode)
            cl_conserved = tuple(
                p.interaction_key
                for p in cl_prevs
                if p.frequency >= conserved_threshold
            )
            family_profiles.append(
                PoseFamilyInteractionProfile(
                    cluster_id=cl.cluster_id,
                    medoid_pose_id=cl.medoid_pose_id,
                    member_pose_count=len(cl.member_pose_ids),
                    prevalences=cl_prevs,
                    conserved_interactions=cl_conserved,
                )
            )

    return InteractionConsensusResult(
        compound_id=compound_id,
        global_prevalences=global_prevs,
        family_profiles=tuple(family_profiles),
        residue_interaction_matrix=res_matrix,
        conserved_core_interactions=conserved_core,
        total_poses=total_poses,
        zero_contact_pose_count=zero_contact_count,
        metadata={
            "key_mode": key_mode,
            "conserved_threshold": conserved_threshold,
        },
    )


__all__ = ["compute_interaction_consensus"]
