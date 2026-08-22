"""Deterministic Decision Profile evaluation and explanation generation."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from .models import (
    CompoundDecision,
    CriterionRole,
    DecisionCampaignResult,
    DecisionPriority,
    DecisionProfile,
)


def _label(key: str, description: str | None) -> str:
    return f"{key} ({description})" if description else key


def evaluate_compound_decision(
    compound_id: str,
    data: Mapping[str, Any],
    profile: DecisionProfile,
) -> CompoundDecision:
    """Evaluate a compound against a Decision Profile and generate justifications."""
    why_positive: list[str] = []
    why_negative: list[str] = []
    warnings: list[str] = []
    recommended_evidence: list[str] = []

    is_rejected = False
    is_held = False

    # 1. Evaluate EXCLUSION criteria
    for key, crit in profile.criteria.items():
        if crit.role != CriterionRole.EXCLUSION:
            continue
        val = data.get(key)
        if val is None:
            continue

        lbl = _label(key, crit.description)
        str_val = str(val).lower().strip()
        if any(rej.lower().strip() == str_val for rej in crit.rejected_values):
            is_rejected = True
            why_negative.append(f"Excluded by filter '{lbl}' (value: {val})")

        if isinstance(val, (int, float)) and math.isfinite(val):
            if crit.min_value is not None and val < crit.min_value:
                is_rejected = True
                why_negative.append(
                    f"Excluded by '{lbl}' (value {val} < min {crit.min_value})"
                )
            if crit.max_value is not None and val > crit.max_value:
                is_rejected = True
                why_negative.append(
                    f"Excluded by '{lbl}' (value {val} > max {crit.max_value})"
                )

    if is_rejected:
        return CompoundDecision(
            compound_id=compound_id,
            priority=DecisionPriority.REJECT,
            composite_score=None,
            rank=None,
            why_positive=(),
            why_negative=tuple(why_negative),
            warnings=(),
            recommended_next_evidence=(),
            evaluations=dict(data),
        )

    # 2. Evaluate MANDATORY criteria
    for key, crit in profile.criteria.items():
        if crit.role != CriterionRole.MANDATORY:
            continue
        val = data.get(key)
        lbl = _label(key, crit.description)
        if val is None:
            is_held = True
            why_negative.append(f"Missing mandatory evidence '{lbl}'")
            rec = profile.default_next_evidence_map.get(key, f"Obtain {lbl} evidence")
            recommended_evidence.append(rec)
            continue

        if isinstance(val, (int, float)) and math.isfinite(val):
            if crit.min_value is not None and val < crit.min_value:
                is_held = True
                why_negative.append(
                    f"Failed mandatory '{lbl}' "
                    f"({val:.2f} < threshold {crit.min_value:.2f})"
                )
            elif crit.max_value is not None and val > crit.max_value:
                is_held = True
                why_negative.append(
                    f"Failed mandatory '{lbl}' "
                    f"({val:.2f} > threshold {crit.max_value:.2f})"
                )
            else:
                why_positive.append(f"Satisfies mandatory '{lbl}' (value: {val:.2f})")

    # 3. Evaluate WARNING criteria
    for key, crit in profile.criteria.items():
        if crit.role != CriterionRole.WARNING:
            continue
        val = data.get(key)
        if val is None:
            continue
        lbl = _label(key, crit.description)
        if isinstance(val, (int, float)) and math.isfinite(val):
            if crit.max_value is not None and val > crit.max_value:
                warnings.append(
                    f"Warning for '{lbl}': "
                    f"value {val:.2f} exceeds threshold {crit.max_value:.2f}"
                )
            if crit.min_value is not None and val < crit.min_value:
                warnings.append(
                    f"Warning for '{lbl}': "
                    f"value {val:.2f} below threshold {crit.min_value:.2f}"
                )

    # 4. Evaluate RANK criteria
    weighted_sum = 0.0
    total_weight = 0.0

    for key, crit in profile.criteria.items():
        if crit.role not in (CriterionRole.RANK, CriterionRole.MANDATORY):
            continue
        val = data.get(key)
        lbl = _label(key, crit.description)
        if val is None or not isinstance(val, (int, float)) or not math.isfinite(val):
            rec_opt: str | None = profile.default_next_evidence_map.get(key)
            if rec_opt and rec_opt not in recommended_evidence:
                recommended_evidence.append(rec_opt)
            continue

        w = crit.weight if crit.weight > 0 else 1.0
        weighted_sum += w * float(val)
        total_weight += w

        if val >= 0.70:
            why_positive.append(f"Strong performance in '{lbl}' (score: {val:.2f})")
        elif val < 0.40:
            why_negative.append(f"Suboptimal performance in '{lbl}' (score: {val:.2f})")

    composite_score = (weighted_sum / total_weight) if total_weight > 0 else None

    if is_held:
        priority = DecisionPriority.HOLD
    elif composite_score is not None and composite_score >= 0.60:
        priority = DecisionPriority.ADVANCE
    elif composite_score is not None:
        priority = DecisionPriority.HOLD
    else:
        priority = DecisionPriority.INSUFFICIENT_DATA

    return CompoundDecision(
        compound_id=compound_id,
        priority=priority,
        composite_score=composite_score,
        rank=None,
        why_positive=tuple(why_positive),
        why_negative=tuple(why_negative),
        warnings=tuple(warnings),
        recommended_next_evidence=tuple(recommended_evidence),
        evaluations=dict(data),
    )


def evaluate_campaign_decisions(
    candidates_data: Mapping[str, Mapping[str, Any]],
    profile: DecisionProfile,
) -> DecisionCampaignResult:
    """Evaluate and rank all campaign candidates under the designated profile."""
    decisions_list: list[CompoundDecision] = []

    for cid, cdata in candidates_data.items():
        dec = evaluate_compound_decision(cid, cdata, profile)
        decisions_list.append(dec)

    def _sort_key(d: CompoundDecision) -> tuple[int, float]:
        if d.priority == DecisionPriority.ADVANCE:
            p_order = 1
        elif d.priority == DecisionPriority.HOLD:
            p_order = 2
        elif d.priority == DecisionPriority.INSUFFICIENT_DATA:
            p_order = 3
        else:
            p_order = 4
        score = d.composite_score if d.composite_score is not None else -1.0
        return (p_order, -score)

    decisions_list.sort(key=_sort_key)

    ranked_decisions: list[CompoundDecision] = []
    current_rank = 1
    advance_count = 0
    hold_count = 0
    reject_count = 0

    for d in decisions_list:
        if d.priority == DecisionPriority.ADVANCE:
            advance_count += 1
        elif d.priority == DecisionPriority.HOLD:
            hold_count += 1
        elif d.priority == DecisionPriority.REJECT:
            reject_count += 1

        ranked_decisions.append(
            CompoundDecision(
                compound_id=d.compound_id,
                priority=d.priority,
                composite_score=d.composite_score,
                rank=current_rank,
                why_positive=d.why_positive,
                why_negative=d.why_negative,
                warnings=d.warnings,
                recommended_next_evidence=d.recommended_next_evidence,
                evaluations=d.evaluations,
            )
        )
        current_rank += 1

    return DecisionCampaignResult(
        profile_name=profile.name,
        profile_version=profile.version,
        total_evaluated=len(ranked_decisions),
        advance_count=advance_count,
        hold_count=hold_count,
        reject_count=reject_count,
        decisions=tuple(ranked_decisions),
    )


__all__ = ["evaluate_campaign_decisions", "evaluate_compound_decision"]
