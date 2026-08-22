"""Acceptance test for multi-fidelity Decision Profile evaluation."""

from __future__ import annotations

from fidelichem.decision.engine import DecisionEngine
from fidelichem.decision.models import DecisionPriority


def test_decision_campaign_full_pipeline() -> None:
    """Verify decision profile triage and deterministic explanations."""
    engine = DecisionEngine()

    profile_dict = {
        "name": "beta_lactamase_screening_v1",
        "version": 1,
        "description": "Standard triage policy for beta-lactamase inhibitors",
        "criteria": {
            "pains": {
                "role": "exclusion",
                "rejected_values": ["true", "1"],
                "description": "PAINS pan-assay filter",
            },
            "docking_consensus": {
                "role": "mandatory",
                "min_value": 0.50,
                "weight": 1.0,
                "description": "Cross-tool docking consensus percentile",
            },
            "key_interactions": {
                "role": "rank",
                "weight": 1.5,
                "description": "SER70 and GLU166 binding site occupancy",
            },
            "md_contact_retention": {
                "role": "rank",
                "weight": 1.2,
                "description": "50ns MD contact retention fraction",
            },
            "synthetic_accessibility": {
                "role": "warning",
                "max_value": 4.5,
                "description": "Synthetic accessibility SA score",
            },
        },
        "default_next_evidence_map": {
            "md_contact_retention": "Submit to MolDynStudio for 50ns MD",
            "key_interactions": "Run DockLens interaction profiling",
            "docking_consensus": "Perform secondary cross-docking",
        },
    }

    profile = engine.load_profile_from_dict(profile_dict)
    assert profile.name == "beta_lactamase_screening_v1"
    assert len(profile.criteria) == 5

    candidates = {
        "C01": {  # Top hit: ADVANCE
            "pains": "false",
            "docking_consensus": 0.96,
            "key_interactions": 0.90,
            "md_contact_retention": 0.85,
            "synthetic_accessibility": 2.2,
        },
        "C02": {  # Strong hit: ADVANCE
            "pains": "false",
            "docking_consensus": 0.88,
            "key_interactions": 0.80,
            "md_contact_retention": 0.75,
            "synthetic_accessibility": 2.8,
        },
        "C03": {  # PAINS excluded: REJECT
            "pains": "true",
            "docking_consensus": 0.99,
            "key_interactions": 0.95,
            "md_contact_retention": 0.90,
            "synthetic_accessibility": 1.8,
        },
        "C04": {  # Missing mandatory docking evidence: HOLD with recommendation
            "pains": "false",
            "docking_consensus": None,
            "key_interactions": 0.85,
            "md_contact_retention": 0.80,
            "synthetic_accessibility": 3.0,
        },
        "C05": {  # Poor docking: HOLD / Low score
            "pains": "false",
            "docking_consensus": 0.35,  # Fails mandatory threshold 0.50
            "key_interactions": 0.20,
            "md_contact_retention": 0.30,
            "synthetic_accessibility": 5.2,  # Triggers warning
        },
    }

    result = engine.evaluate_campaign(candidates, profile)
    assert result.total_evaluated == 5
    assert result.advance_count == 2
    assert result.reject_count == 1
    assert result.hold_count == 2

    # Verify rank 1 is C01
    d_top = result.decisions[0]
    assert d_top.compound_id == "C01"
    assert d_top.priority == DecisionPriority.ADVANCE
    assert d_top.composite_score is not None
    assert d_top.composite_score > 0.85
    assert len(d_top.why_positive) >= 2
    assert len(d_top.warnings) == 0

    # Verify C03 is REJECT with explanation
    d_rej = next(d for d in result.decisions if d.compound_id == "C03")
    assert d_rej.priority == DecisionPriority.REJECT
    assert len(d_rej.why_negative) >= 1
    assert "pains" in d_rej.why_negative[0].lower()

    # Verify C04 is HOLD with recommended next evidence
    d_hold = next(d for d in result.decisions if d.compound_id == "C04")
    assert d_hold.priority == DecisionPriority.HOLD
    assert len(d_hold.recommended_next_evidence) > 0
    assert any("docking" in r.lower() for r in d_hold.recommended_next_evidence)

    # Verify C05 has SA score warning
    d_c05 = next(d for d in result.decisions if d.compound_id == "C05")
    assert d_c05.priority == DecisionPriority.HOLD
    assert len(d_c05.warnings) > 0
    assert any("synthetic_accessibility" in w for w in d_c05.warnings)
