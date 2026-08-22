"""Unified facade coordinating score consensus and Pareto frontiers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from fidelichem.domain.table_importer import ScoreDirection

from .agreement import (
    compute_campaign_agreement,
    compute_molecule_agreement,
)
from .consensus import compute_score_consensus
from .models import (
    CampaignAgreement,
    MoleculeAgreement,
    ParetoFrontierResult,
    ScoreConsensusResult,
)
from .pareto import compute_pareto_fronts


class AnalyticsEngine:
    """Central analytics engine executing multi-objective evaluations."""

    def score_consensus(
        self,
        compound_percentiles: Mapping[str, Mapping[str, float | None]],
        compound_ranks: Mapping[str, Mapping[str, int | None]] | None = None,
        compound_raw_scores: Mapping[str, Mapping[str, float | None]] | None = None,
        weights: Mapping[str, float] | None = None,
    ) -> list[ScoreConsensusResult]:
        """Compute score consensus across multiple docking or property methods."""
        return compute_score_consensus(
            compound_percentiles=compound_percentiles,
            compound_ranks=compound_ranks,
            compound_raw_scores=compound_raw_scores,
            weights=weights,
        )

    def molecule_agreement(
        self,
        percentiles: Mapping[str, float | None],
        compound_id: str,
        high_threshold: float = 0.15,
        mod_threshold: float = 0.35,
    ) -> MoleculeAgreement:
        """Classify scoring agreement for a specific molecule."""
        return compute_molecule_agreement(
            percentiles=percentiles,
            compound_id=compound_id,
            high_threshold=high_threshold,
            mod_threshold=mod_threshold,
        )

    def campaign_agreement(
        self,
        score_table: Mapping[str, Mapping[str, float | None]],
        top_k_fraction: float = 0.1,
    ) -> CampaignAgreement:
        """Compute pairwise Spearman, Kendall, and top-k agreement matrix."""
        return compute_campaign_agreement(
            score_table=score_table,
            top_k_fraction=top_k_fraction,
        )

    def pareto_frontier(
        self,
        candidates: Mapping[str, Mapping[str, float | None]],
        dimensions: Sequence[str],
        directions: Mapping[str, ScoreDirection],
    ) -> ParetoFrontierResult:
        """Calculate multi-objective Pareto frontiers and non-dominated ranking."""
        return compute_pareto_fronts(
            candidates=candidates,
            dimensions=dimensions,
            directions=directions,
        )


__all__ = ["AnalyticsEngine"]
