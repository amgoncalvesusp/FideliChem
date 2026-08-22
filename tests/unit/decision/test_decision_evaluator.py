"""Unit tests for deterministic Decision Profile evaluation."""

from __future__ import annotations

from fidelichem.decision.evaluator import evaluate_compound_decision
from fidelichem.decision.models import (
    CriterionRole,
    DecisionCriterion,
    DecisionPriority,
    DecisionProfile,
)


def _build_test_profile() -> DecisionProfile:
    return DecisionProfile(
        name="kinase_screening_profile",
        version=1,
        criteria={
            "pains": DecisionCriterion(
                key="pains",
                role=CriterionRole.EXCLUSION,
                rejected_values=("true", "1", "yes"),
                description="PAINS substructure filter",
            ),
            "docking_consensus": DecisionCriterion(
                key="docking_consensus",
                role=CriterionRole.MANDATORY,
                min_value=0.50,
                weight=1.0,
                description="Docking consensus percentile",
            ),
            "key_interactions": DecisionCriterion(
                key="key_interactions",
                role=CriterionRole.RANK,
                weight=1.5,
                description="Key active site interaction occupancy",
            ),
            "sa_score": DecisionCriterion(
                key="sa_score",
                role=CriterionRole.WARNING,
                max_value=4.5,
                description="Synthetic accessibility threshold",
            ),
        },
        default_next_evidence_map={
            "md_stability": "Run 50ns molecular dynamics trajectory",
            "key_interactions": "Run DockLens interaction profiling",
        },
    )


def test_advance_candidate_with_explanations() -> None:
    profile = _build_test_profile()
    data = {
        "pains": "false",
        "docking_consensus": 0.95,
        "key_interactions": 0.90,
        "sa_score": 2.1,
    }

    decision = evaluate_compound_decision("CMPD_01", data, profile)
    assert decision.priority == DecisionPriority.ADVANCE
    assert decision.composite_score is not None
    assert decision.composite_score > 0.85
    assert len(decision.why_positive) >= 1
    assert any("docking_consensus" in exp for exp in decision.why_positive)
    assert len(decision.warnings) == 0


def test_reject_candidate_due_to_exclusion() -> None:
    profile = _build_test_profile()
    data = {
        "pains": "true",
        "docking_consensus": 0.98,
        "key_interactions": 0.95,
    }

    decision = evaluate_compound_decision("CMPD_02", data, profile)
    assert decision.priority == DecisionPriority.REJECT
    assert any("pains" in exp.lower() for exp in decision.why_negative)


def test_hold_candidate_and_recommended_next_evidence() -> None:
    profile = _build_test_profile()
    # Missing mandatory docking consensus and missing key interactions
    data = {
        "pains": "false",
        "docking_consensus": 0.30,  # Fails mandatory min_value 0.50
        "sa_score": 5.2,  # Triggers warning max_value 4.5
    }

    decision = evaluate_compound_decision("CMPD_03", data, profile)
    assert decision.priority == DecisionPriority.HOLD
    assert any("docking_consensus" in exp for exp in decision.why_negative)
    assert any("sa_score" in w for w in decision.warnings)
    assert len(decision.recommended_next_evidence) > 0
