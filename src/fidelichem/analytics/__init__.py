"""Analytics engine for multi-objective consensus and Pareto optimization."""

from .agreement import (
    compute_campaign_agreement,
    compute_kendall_tau,
    compute_molecule_agreement,
    compute_spearman_correlation,
)
from .consensus import compute_score_consensus
from .engine import AnalyticsEngine
from .models import (
    AgreementLevel,
    CampaignAgreement,
    MoleculeAgreement,
    ParetoFrontierResult,
    ScoreConsensusResult,
)
from .pareto import compute_pareto_fronts

__all__ = [
    "AgreementLevel",
    "AnalyticsEngine",
    "CampaignAgreement",
    "MoleculeAgreement",
    "ParetoFrontierResult",
    "ScoreConsensusResult",
    "compute_campaign_agreement",
    "compute_kendall_tau",
    "compute_molecule_agreement",
    "compute_pareto_fronts",
    "compute_score_consensus",
    "compute_spearman_correlation",
]
