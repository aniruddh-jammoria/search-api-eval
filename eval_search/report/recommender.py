from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path

from anthropic import Anthropic

from eval_search.models import AggregatedMetrics, EvaluationRun

_PROMPT_PATH = Path(__file__).parent / "recommendation_prompt.md"
_MODEL = "claude-haiku-4-5-20251001"


def _build_summary(metrics: list[AggregatedMetrics]) -> list[dict]:
    """Aggregate per-topic metrics into one row per endpoint for the prompt."""
    grouped: dict[str, list[AggregatedMetrics]] = defaultdict(list)
    for m in metrics:
        grouped[m.endpoint_id].append(m)

    summary = []
    for ep_id, ms in sorted(grouped.items()):
        def _avg(field: str) -> float | None:
            vals = [getattr(m, field) for m in ms if getattr(m, field) is not None]
            return round(statistics.mean(vals), 4) if vals else None

        def _sum(field: str) -> float:
            return round(sum(getattr(m, field, 0) or 0 for m in ms), 6)

        summary.append({
            "endpoint_id": ep_id,
            "avg_relevance_claude": _avg("avg_relevance_claude"),
            "avg_relevance_openai": _avg("avg_relevance_openai"),
            "avg_newsworthiness_claude": _avg("avg_newsworthiness_claude"),
            "avg_newsworthiness_openai": _avg("avg_newsworthiness_openai"),
            "judge_relevance_correlation": _avg("judge_relevance_correlation"),
            "pct_within_lookback": _avg("pct_within_lookback"),
            "median_age_hours": _avg("median_age_hours"),
            "search_cost_usd": _sum("search_cost_usd"),
            "summarization_cost_usd": _sum("summarization_cost_usd"),
            "p50_latency_ms": _avg("p50_latency_ms"),
            "cost_per_relevant_article": _avg("cost_per_relevant_article"),
        })
    return summary


def generate_recommendation(
    metrics: list[AggregatedMetrics],
    run: EvaluationRun,
    api_key: str,
) -> str:
    prompt = _PROMPT_PATH.read_text(encoding="utf-8").strip()
    summary = _build_summary(metrics)
    full_prompt = (
        prompt
        + "\n\n---\n\n"
        + json.dumps(summary, indent=2)
    )

    client = Anthropic(api_key=api_key)
    response = client.messages.create(
        model=_MODEL,
        max_tokens=400,
        messages=[{"role": "user", "content": full_prompt}],
    )
    return response.content[0].text.strip()
