"""Decision Engine facade coordinating profile parsing and evaluation."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from .evaluator import evaluate_campaign_decisions, evaluate_compound_decision
from .models import (
    CompoundDecision,
    CriterionRole,
    DecisionCampaignResult,
    DecisionCriterion,
    DecisionProfile,
)


class DecisionEngine:
    """Decision engine managing policies, triage, and multi-fidelity ranking."""

    def load_profile_from_dict(self, data: Mapping[str, Any]) -> DecisionProfile:
        """Parse and validate a DecisionProfile from a mapping dictionary."""
        name = str(data.get("name") or "custom_decision_profile")
        version = int(data.get("version") or 1)
        description = data.get("description")

        criteria_dict: dict[str, DecisionCriterion] = {}
        raw_criteria = data.get("criteria") or {}
        for k, v in raw_criteria.items():
            if isinstance(v, dict):
                role_str = str(v.get("role") or "rank").lower()
                try:
                    role = CriterionRole(role_str)
                except ValueError:
                    role = CriterionRole.RANK

                weight = float(v.get("weight") or 1.0)
                min_v = (
                    float(v["min_value"])
                    if "min_value" in v and v["min_value"] is not None
                    else None
                )
                max_v = (
                    float(v["max_value"])
                    if "max_value" in v and v["max_value"] is not None
                    else None
                )
                allowed = tuple(str(x) for x in v.get("allowed_values", []))
                rejected = tuple(str(x) for x in v.get("rejected_values", []))
                desc = v.get("description")

                criteria_dict[k] = DecisionCriterion(
                    key=k,
                    role=role,
                    weight=weight,
                    min_value=min_v,
                    max_value=max_v,
                    allowed_values=allowed,
                    rejected_values=rejected,
                    description=desc,
                )

        next_map = {
            str(k): str(v)
            for k, v in (data.get("default_next_evidence_map") or {}).items()
        }

        return DecisionProfile(
            name=name,
            version=version,
            description=str(description) if description else None,
            criteria=criteria_dict,
            default_next_evidence_map=next_map,
        )

    def load_profile_from_json(self, json_str: str) -> DecisionProfile:
        """Parse DecisionProfile from JSON string."""
        data = json.loads(json_str)
        return self.load_profile_from_dict(data)

    def evaluate_compound(
        self,
        compound_id: str,
        data: Mapping[str, Any],
        profile: DecisionProfile,
    ) -> CompoundDecision:
        """Evaluate a single candidate against a Decision Profile."""
        return evaluate_compound_decision(compound_id, data, profile)

    def evaluate_campaign(
        self,
        candidates_data: Mapping[str, Mapping[str, Any]],
        profile: DecisionProfile,
    ) -> DecisionCampaignResult:
        """Evaluate and rank an entire virtual screening candidate set."""
        return evaluate_campaign_decisions(candidates_data, profile)


__all__ = ["DecisionEngine"]
