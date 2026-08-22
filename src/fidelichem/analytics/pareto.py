"""Multi-objective Pareto frontier analysis and non-dominated candidate ranking."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

from fidelichem.domain.table_importer import ScoreDirection

from .models import ParetoFrontierResult


def _dominates(
    vals_a: Mapping[str, float | None],
    vals_b: Mapping[str, float | None],
    dimensions: Sequence[str],
    directions: Mapping[str, ScoreDirection],
) -> bool:
    """Return True if candidate A strictly Pareto-dominates candidate B."""
    at_least_one_strictly_better = False

    for dim in dimensions:
        va = vals_a.get(dim)
        vb = vals_b.get(dim)

        if va is None or vb is None or not math.isfinite(va) or not math.isfinite(vb):
            return False

        direction = directions.get(dim, ScoreDirection.HIGHER_BETTER)

        if direction == ScoreDirection.HIGHER_BETTER:
            if va < vb:
                return False
            if va > vb:
                at_least_one_strictly_better = True
        else:  # LOWER_BETTER
            if va > vb:
                return False
            if va < vb:
                at_least_one_strictly_better = True

    return at_least_one_strictly_better


def compute_pareto_fronts(
    candidates: Mapping[str, Mapping[str, float | None]],
    dimensions: Sequence[str],
    directions: Mapping[str, ScoreDirection],
) -> ParetoFrontierResult:
    """Execute fast non-dominated sorting across multi-objective dimensions.

    Candidates with missing values in specified dimensions are partitioned
    into trailing tiers and never permitted to dominate complete records.
    """
    dims = tuple(dimensions)
    complete_cands: list[str] = []
    incomplete_cands: list[str] = []

    for cid, vals in candidates.items():
        if all(
            vals.get(d) is not None and math.isfinite(vals.get(d))  # type: ignore[arg-type]
            for d in dims
        ):
            complete_cands.append(cid)
        else:
            incomplete_cands.append(cid)

    # Fast non-dominated sorting on complete candidates
    dominates_map: dict[str, list[str]] = {cid: [] for cid in complete_cands}
    domination_count: dict[str, int] = {cid: 0 for cid in complete_cands}
    fronts: list[list[str]] = [[]]

    for i, p in enumerate(complete_cands):
        for j in range(i + 1, len(complete_cands)):
            q = complete_cands[j]
            p_dom_q = _dominates(candidates[p], candidates[q], dims, directions)
            q_dom_p = _dominates(candidates[q], candidates[p], dims, directions)

            if p_dom_q:
                dominates_map[p].append(q)
                domination_count[q] += 1
            elif q_dom_p:
                dominates_map[q].append(p)
                domination_count[p] += 1

        if domination_count[p] == 0:
            fronts[0].append(p)

    current_front_idx = 0
    while current_front_idx < len(fronts) and fronts[current_front_idx]:
        next_front: list[str] = []
        for p in fronts[current_front_idx]:
            for q in dominates_map[p]:
                domination_count[q] -= 1
                if domination_count[q] == 0:
                    next_front.append(q)
        if next_front:
            fronts.append(next_front)
        current_front_idx += 1

    pareto_ranks: dict[str, int] = {}
    for rank_idx, front in enumerate(fronts, start=1):
        for cid in front:
            pareto_ranks[cid] = rank_idx

    # Assign trailing rank to incomplete candidates
    max_rank = len(fronts) + 1 if fronts and fronts[0] else 1
    for cid in incomplete_cands:
        pareto_ranks[cid] = max_rank

    frontier_compounds = tuple(fronts[0]) if fronts and fronts[0] else ()
    dominated_compounds = tuple(
        cid for cid in candidates if cid not in set(frontier_compounds)
    )

    return ParetoFrontierResult(
        dimensions=dims,
        directions=dict(directions),
        frontier_compounds=frontier_compounds,
        dominated_compounds=dominated_compounds,
        pareto_ranks=pareto_ranks,
        candidate_values=dict(candidates),
    )


__all__ = ["compute_pareto_fronts"]
