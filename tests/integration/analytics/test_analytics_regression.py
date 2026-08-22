"""Scientific regression suite validating multi-objective analytics."""

from __future__ import annotations

import pytest

from fidelichem.analytics.engine import AnalyticsEngine
from fidelichem.analytics.models import AgreementLevel
from fidelichem.domain.scoring import ScoreDefinition
from fidelichem.domain.table_importer import ScoreDirection
from fidelichem.scoring.normalizer import ScoreNormalizer


def test_scientific_analytics_full_pipeline_regression() -> None:
    """Execute end-to-end multi-objective analytics workflow."""

    engine = AnalyticsEngine()
    normalizer = ScoreNormalizer()

    # 1. Raw scores from 3 docking runs + physicochemical metrics for 6 candidates
    raw_chemplp = {
        "M1": 95.0,
        "M2": 88.0,
        "M3": 82.0,
        "M4": 75.0,
        "M5": 60.0,
        "M6": 50.0,
    }
    raw_vina = {
        "M1": -10.5,
        "M2": -9.8,
        "M3": -8.5,
        "M4": -7.2,
        "M5": -6.0,
        "M6": -5.5,
    }
    raw_asp = {
        "M1": 42.0,
        "M2": 38.0,
        "M3": 25.0,
        "M4": 30.0,
        "M5": 15.0,
        "M6": None,
    }  # M6 missing ASP

    # 2. Normalize raw scores to direction-aware percentiles (1.0 = best candidate)
    def_chemplp = ScoreDefinition(
        key="gold.chemplp",
        display_name="ChemPLP",
        direction=ScoreDirection.HIGHER_BETTER,
    )
    def_vina = ScoreDefinition(
        key="vina.affinity",
        display_name="Vina Affinity",
        direction=ScoreDirection.LOWER_BETTER,
    )
    def_asp = ScoreDefinition(
        key="gold.asp",
        display_name="ASP",
        direction=ScoreDirection.HIGHER_BETTER,
    )

    records_chemplp = [{"cid": cid, "val": v} for cid, v in raw_chemplp.items()]
    records_vina = [{"cid": cid, "val": v} for cid, v in raw_vina.items()]
    records_asp = [{"cid": cid, "val": v} for cid, v in raw_asp.items()]

    obs_chemplp, _ = normalizer.normalize_values(
        records_chemplp,
        definition=def_chemplp,
        scope_key="target_egfr",
        value_key="val",
        entity_key="cid",
    )
    obs_vina, _ = normalizer.normalize_values(
        records_vina,
        definition=def_vina,
        scope_key="target_egfr",
        value_key="val",
        entity_key="cid",
    )
    obs_asp, _ = normalizer.normalize_values(
        records_asp,
        definition=def_asp,
        scope_key="target_egfr",
        value_key="val",
        entity_key="cid",
    )

    pct_chemplp = {o.entity_reference: o.percentile for o in obs_chemplp}
    pct_vina = {o.entity_reference: o.percentile for o in obs_vina}
    pct_asp = {o.entity_reference: o.percentile for o in obs_asp}

    percentile_table: dict[str, dict[str, float | None]] = {
        cid: {
            "chemplp": pct_chemplp.get(cid),
            "vina": pct_vina.get(cid),
            "asp": pct_asp.get(cid),
        }
        for cid in raw_chemplp
    }

    # 3. Score consensus calculation
    consensus_results = engine.score_consensus(percentile_table)
    assert len(consensus_results) == 6

    # Top candidate M1 has highest percentiles across all 3 methods
    top_cand = consensus_results[0]
    assert top_cand.compound_id == "M1"
    assert top_cand.median_percentile == 1.0
    assert top_cand.method_count == 3

    # 4. Molecule agreement classification
    agr_m1 = engine.molecule_agreement(percentile_table["M1"], compound_id="M1")
    assert agr_m1.agreement_level == AgreementLevel.HIGH
    assert agr_m1.percentile_range == 0.0

    # 5. Campaign global agreement
    raw_score_table = {
        cid: {
            "chemplp": raw_chemplp[cid],
            "vina": -raw_vina[cid],  # oriented positive for rank correlation
            "asp": raw_asp[cid],
        }
        for cid in raw_chemplp
    }
    camp_agr = engine.campaign_agreement(raw_score_table, top_k_fraction=0.33)
    assert pytest.approx(camp_agr.spearman_matrix["chemplp"]["vina"], rel=1e-2) == 1.0

    # 6. Multi-objective Pareto frontier analysis
    # Candidates with docking consensus, QED, SA score, and MD RMSD
    candidate_profiles = {
        "M1": {
            "docking": top_cand.median_percentile,
            "qed": 0.85,
            "sa_score": 2.1,
            "rmsd": 0.12,
        },
        "M2": {"docking": 0.80, "qed": 0.92, "sa_score": 1.6, "rmsd": 0.10},
        "M3": {"docking": 0.60, "qed": 0.70, "sa_score": 2.8, "rmsd": 0.18},
        "M4": {"docking": 0.50, "qed": 0.60, "sa_score": 3.2, "rmsd": 0.25},
        "M5": {"docking": 0.20, "qed": 0.40, "sa_score": 4.5, "rmsd": 0.35},
        "M6": {
            "docking": 0.10,
            "qed": 0.30,
            "sa_score": None,
            "rmsd": 0.40,
        },  # incomplete
    }

    pareto_res = engine.pareto_frontier(
        candidates=candidate_profiles,
        dimensions=("docking", "qed", "sa_score", "rmsd"),
        directions={
            "docking": ScoreDirection.HIGHER_BETTER,
            "qed": ScoreDirection.HIGHER_BETTER,
            "sa_score": ScoreDirection.LOWER_BETTER,
            "rmsd": ScoreDirection.LOWER_BETTER,
        },
    )

    # Both M1 (best docking) and M2 (best QED + best SA + best RMSD)
    # form the non-dominated Pareto front
    assert "M1" in pareto_res.frontier_compounds
    assert "M2" in pareto_res.frontier_compounds
    assert pareto_res.pareto_ranks["M1"] == 1
    assert pareto_res.pareto_ranks["M2"] == 1

    # Incomplete M6 is ranked last
    assert pareto_res.pareto_ranks["M6"] > 1
