"""ScoreRegistry service managing standard scoring functions and semantics."""

from __future__ import annotations

import re

from fidelichem.domain.scoring import (
    ComparabilityScope,
    ScoreDefinition,
    ScoreDirection,
)

_BUILTIN_DEFINITIONS: tuple[ScoreDefinition, ...] = (
    ScoreDefinition(
        key="gold.chemplp",
        display_name="GOLD ChemPLP",
        source_engine="gold",
        direction=ScoreDirection.HIGHER_BETTER,
        unit="fitness",
        comparability_scope=ComparabilityScope.RUN,
        description="Piecewise Linear Potential empirical fitness function in GOLD",
        is_builtin=True,
    ),
    ScoreDefinition(
        key="gold.goldscore",
        display_name="GOLD GoldScore",
        source_engine="gold",
        direction=ScoreDirection.HIGHER_BETTER,
        unit="fitness",
        comparability_scope=ComparabilityScope.RUN,
        description="Original force field and hydrogen bonding fitness in GOLD",
        is_builtin=True,
    ),
    ScoreDefinition(
        key="gold.chemscore",
        display_name="GOLD ChemScore",
        source_engine="gold",
        direction=ScoreDirection.HIGHER_BETTER,
        unit="fitness",
        comparability_scope=ComparabilityScope.RUN,
        description="Empirical binding affinity function in GOLD",
        is_builtin=True,
    ),
    ScoreDefinition(
        key="gold.asp",
        display_name="GOLD ASP",
        source_engine="gold",
        direction=ScoreDirection.HIGHER_BETTER,
        unit="fitness",
        comparability_scope=ComparabilityScope.RUN,
        description="Astex Statistical Potential knowledge-based scoring in GOLD",
        is_builtin=True,
    ),
    ScoreDefinition(
        key="vina.affinity",
        display_name="AutoDock Vina Affinity",
        source_engine="vina",
        direction=ScoreDirection.LOWER_BETTER,
        unit="kcal/mol",
        comparability_scope=ComparabilityScope.RUN,
        description="Calculated binding free energy in AutoDock Vina",
        is_builtin=True,
    ),
    ScoreDefinition(
        key="vina.score",
        display_name="AutoDock Vina Score",
        source_engine="vina",
        direction=ScoreDirection.LOWER_BETTER,
        unit="kcal/mol",
        comparability_scope=ComparabilityScope.RUN,
        description="Empirical energy score in AutoDock Vina",
        is_builtin=True,
    ),
    ScoreDefinition(
        key="glide.gscore",
        display_name="Glide GScore",
        source_engine="glide",
        direction=ScoreDirection.LOWER_BETTER,
        unit="kcal/mol",
        comparability_scope=ComparabilityScope.RUN,
        description="Empirical GlideScore free energy approximation",
        is_builtin=True,
    ),
    ScoreDefinition(
        key="glide.emodel",
        display_name="Glide Emodel",
        source_engine="glide",
        direction=ScoreDirection.LOWER_BETTER,
        unit="kcal/mol",
        comparability_scope=ComparabilityScope.RUN,
        description="Glide conformational selection energy",
        is_builtin=True,
    ),
    ScoreDefinition(
        key="docking.plp",
        display_name="Docking PLP Score",
        source_engine="generic_docking",
        direction=ScoreDirection.HIGHER_BETTER,
        unit="fitness",
        comparability_scope=ComparabilityScope.RUN,
        description="Generic Piecewise Linear Potential fitness score",
        is_builtin=True,
    ),
    ScoreDefinition(
        key="docking.score",
        display_name="Docking Energy Score",
        source_engine="generic_docking",
        direction=ScoreDirection.LOWER_BETTER,
        unit="kcal/mol",
        comparability_scope=ComparabilityScope.RUN,
        description="Generic docking binding energy approximation",
        is_builtin=True,
    ),
)


class ScoreRegistry:
    """Registry maintaining known scoring function definitions and directionality."""

    def __init__(self) -> None:
        self._definitions: dict[str, ScoreDefinition] = {}

    @classmethod
    def create_default(cls) -> ScoreRegistry:
        """Create a registry preloaded with standard scientific scoring functions."""
        registry = cls()
        for defn in _BUILTIN_DEFINITIONS:
            registry.register(defn)
        return registry

    def register(
        self,
        definition: ScoreDefinition,
        *,
        allow_override: bool = False,
    ) -> None:
        """Register a scoring function definition."""
        key = definition.key
        if key in self._definitions and not allow_override:
            raise ValueError(f"Score definition '{key}' is already registered")
        self._definitions[key] = definition

    def has(self, score_key: str) -> bool:
        """Check if score key is registered."""
        return score_key in self._definitions

    def get(self, score_key: str) -> ScoreDefinition:
        """Retrieve score definition or raise KeyError."""
        if score_key not in self._definitions:
            raise KeyError(f"Score definition '{score_key}' not found in registry")
        return self._definitions[score_key]

    def list_definitions(self) -> tuple[ScoreDefinition, ...]:
        """Return all registered score definitions sorted by key."""
        return tuple(self._definitions[k] for k in sorted(self._definitions.keys()))

    def resolve_or_infer(
        self,
        score_key: str,
        *,
        direction: ScoreDirection | None = None,
        unit: str | None = None,
    ) -> ScoreDefinition:
        """Return registered definition or infer safe directionality heuristically."""
        if score_key in self._definitions:
            existing = self._definitions[score_key]
            if direction is not None and existing.direction != direction:
                return ScoreDefinition(
                    key=existing.key,
                    display_name=existing.display_name,
                    source_engine=existing.source_engine,
                    direction=direction,
                    unit=unit or existing.unit,
                    comparability_scope=existing.comparability_scope,
                    description=existing.description,
                )
            return existing

        # Heuristic inference for unknown score functions
        inferred_direction = direction
        if inferred_direction is None:
            lower_key = score_key.lower()
            if any(
                k in lower_key
                for k in ("plp", "fitness", "goldscore", "chemscore", "asp")
            ):
                inferred_direction = ScoreDirection.HIGHER_BETTER
            else:
                inferred_direction = ScoreDirection.LOWER_BETTER

        inferred_engine = (
            score_key.split(".")[0] if "." in score_key else "user_defined"
        )
        display_name = re.sub(r"[._-]+", " ", score_key).title()

        return ScoreDefinition(
            key=score_key,
            display_name=display_name,
            source_engine=inferred_engine,
            direction=inferred_direction,
            unit=unit,
            comparability_scope=ComparabilityScope.RUN,
            description=f"Inferred score definition for {score_key}",
        )


__all__ = ["ScoreRegistry"]
