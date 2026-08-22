"""Domain models for interaction consensus and contact prevalence."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import Field

from fidelichem.domain.models import DomainModel


class InteractionPrevalence(DomainModel):
    """Prevalence and geometrical summary for an interaction key."""

    interaction_key: str
    target_name: str = "target"
    residue_name: str
    interaction_type: str
    observed_count: int = Field(ge=0, strict=True)
    total_poses: int = Field(ge=1, strict=True)
    frequency: float = Field(ge=0.0, le=1.0)
    mean_distance: float | None = None
    min_distance: float | None = None
    mean_angle: float | None = None


class PoseFamilyInteractionProfile(DomainModel):
    """Mechanistic interaction profile specific to a structural pose cluster."""

    cluster_id: int
    medoid_pose_id: str
    member_pose_count: int = Field(ge=1, strict=True)
    prevalences: tuple[InteractionPrevalence, ...] = Field(default_factory=tuple)
    conserved_interactions: tuple[str, ...] = Field(default_factory=tuple)


class InteractionConsensusResult(DomainModel):
    """Consensus analysis of intermolecular interactions across poses."""

    compound_id: str
    global_prevalences: tuple[InteractionPrevalence, ...] = Field(default_factory=tuple)
    family_profiles: tuple[PoseFamilyInteractionProfile, ...] = Field(
        default_factory=tuple
    )
    residue_interaction_matrix: Mapping[str, Mapping[str, float]] = Field(
        default_factory=dict
    )
    conserved_core_interactions: tuple[str, ...] = Field(default_factory=tuple)
    total_poses: int = Field(ge=0, strict=True)
    zero_contact_pose_count: int = Field(ge=0, default=0, strict=True)
    metadata: Mapping[str, Any] = Field(default_factory=dict)


__all__ = [
    "InteractionConsensusResult",
    "InteractionPrevalence",
    "PoseFamilyInteractionProfile",
]
