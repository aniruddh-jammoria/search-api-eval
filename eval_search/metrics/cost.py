from __future__ import annotations

from eval_search.config import PRICING_TABLE


def estimate_cost(
    endpoint_id: str,
    num_calls: int = 1,
    api_reported_cost: float | None = None,
) -> float:
    """Return estimated USD cost for num_calls to this endpoint."""
    pricing = PRICING_TABLE.get(endpoint_id)
    if pricing is None:
        return 0.0
    if pricing.unit == "from_response" and api_reported_cost is not None:
        return round(api_reported_cost, 6)
    if pricing.cost_per_call is None:
        return 0.0
    return round(pricing.cost_per_call * pricing.credits_per_call * num_calls, 6)


def cost_per_relevant_article(
    total_cost: float,
    avg_relevance_scores: list[float],
    min_relevance: float = 3.0,
) -> float | None:
    relevant = [s for s in avg_relevance_scores if s >= min_relevance]
    if not relevant or total_cost == 0:
        return None
    return round(total_cost / len(relevant), 6)
