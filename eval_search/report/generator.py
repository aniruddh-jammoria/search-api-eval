from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from eval_search.config import PRICING_TABLE
from eval_search.judges.claude_judge import ClaudeJudge
from eval_search.judges.openai_judge import OpenAIJudge
from eval_search.judges.prompts import NEWSWORTHINESS_PROMPT, RELEVANCE_PROMPT
from eval_search.models import AggregatedMetrics, EvaluationRun
from eval_search.report import charts as chart_mod

_TEMPLATES_DIR = Path(__file__).parent / "templates"


def _chart_div(fig) -> str:
    return fig.to_html(full_html=False, include_plotlyjs=False)


def _pricing_label(endpoint_id: str) -> str:
    p = PRICING_TABLE.get(endpoint_id)
    if p is None:
        return "unknown"
    if p.unit == "from_response":
        return "from API response (exact)"
    if p.cost_per_call is None:
        return "—"
    base = f"${p.cost_per_call:.4f}"
    if p.credits_per_call > 1:
        base += f" × {p.credits_per_call} credits"
    return base


def generate_report(run: EvaluationRun, metrics: list[AggregatedMetrics]) -> str:
    # Summary rows: aggregate metrics across topics per endpoint
    endpoint_totals: dict[str, list[AggregatedMetrics]] = defaultdict(list)
    for m in metrics:
        endpoint_totals[m.endpoint_id].append(m)

    summary_rows: list[AggregatedMetrics] = []
    for ep_id, ms in sorted(endpoint_totals.items()):
        def _avg(field: str) -> float | None:
            vals = [getattr(m, field) for m in ms if getattr(m, field) is not None]
            return statistics.mean(vals) if vals else None

        def _sum(field: str) -> float:
            return sum(getattr(m, field, 0) or 0 for m in ms)

        def _corr() -> float | None:
            vals = [m.judge_relevance_correlation for m in ms if m.judge_relevance_correlation is not None]
            return statistics.mean(vals) if vals else None

        summary_rows.append(
            AggregatedMetrics(
                provider_id=ms[0].provider_id,
                endpoint_id=ep_id,
                topic_category=None,
                avg_recency_score=_avg("avg_recency_score") or 0.0,
                pct_within_lookback=_avg("pct_within_lookback") or 0.0,
                median_age_hours=_avg("median_age_hours"),
                avg_relevance_claude=_avg("avg_relevance_claude"),
                avg_relevance_openai=_avg("avg_relevance_openai"),
                judge_relevance_correlation=_corr(),
                avg_newsworthiness_claude=_avg("avg_newsworthiness_claude"),
                avg_newsworthiness_openai=_avg("avg_newsworthiness_openai"),
                search_cost_usd=_sum("search_cost_usd"),
                summarization_cost_usd=_sum("summarization_cost_usd"),
                judge_cost_usd=_sum("judge_cost_usd"),
                total_cost_usd=_sum("total_cost_usd"),
                cost_per_relevant_article=_avg("cost_per_relevant_article"),
                p50_latency_ms=_avg("p50_latency_ms") or 0.0,
                p95_latency_ms=_avg("p95_latency_ms") or 0.0,
            )
        )

    # Collect all EvaluatedResults for correlation chart
    all_evaluated = [ev for ep in run.endpoint_results if not ep.error for ev in ep.results]

    # Build charts — all return plotly figures, convert to HTML divs
    chart_divs: dict[str, str] = {
        "recency_stacked": _chart_div(chart_mod.recency_stacked_bar(run.endpoint_results)),
        "age_box": _chart_div(chart_mod.age_box_plot(run.endpoint_results)),
        "relevance_claude":      _chart_div(chart_mod.relevance_heatmap(metrics, "claude_haiku")),
        "relevance_openai":      _chart_div(chart_mod.relevance_heatmap(metrics, "gpt4o_mini")),
        "newsworthiness_claude": _chart_div(chart_mod.newsworthiness_heatmap(metrics, "claude_haiku")),
        "newsworthiness_openai": _chart_div(chart_mod.newsworthiness_heatmap(metrics, "gpt4o_mini")),
        "judge_correlation":     _chart_div(chart_mod.judge_correlation_scatter(all_evaluated)),
        "cost": _chart_div(chart_mod.cost_bar(metrics)),
        "latency": _chart_div(chart_mod.latency_box_plot(run.endpoint_results)),
    }

    # Build raw rows for the data explorer table
    raw_rows: list[dict[str, Any]] = []
    for ep in run.endpoint_results:
        if ep.error:
            continue
        for ev in ep.results:
            c_rel = next((s.relevance for s in ev.judge_scores if s.judge_id == "claude_haiku"), None)
            o_rel = next((s.relevance for s in ev.judge_scores if s.judge_id == "gpt4o_mini"), None)
            c_news = next((s.newsworthiness for s in ev.judge_scores if s.judge_id == "claude_haiku"), None)
            o_news = next((s.newsworthiness for s in ev.judge_scores if s.judge_id == "gpt4o_mini"), None)
            raw_rows.append(
                dict(
                    endpoint_id=ep.endpoint_id,
                    topic=ep.topic_category.value,
                    title=ev.result.title,
                    url=ev.result.url,
                    date=ev.result.raw_date_str or "",
                    recency_score=ev.recency_score,
                    rel_claude=c_rel,
                    rel_openai=o_rel,
                    news_claude=c_news,
                    news_openai=o_news,
                    summary=ev.result.summary or "",
                )
            )

    env = Environment(loader=FileSystemLoader(str(_TEMPLATES_DIR)), autoescape=False)
    template = env.get_template("report.html.j2")

    return template.render(
        run=run,
        generated_at=datetime.now(timezone.utc),
        summary_rows=summary_rows,
        charts=chart_divs,
        raw_rows=raw_rows,
        pricing={ep_id: _pricing_label(ep_id) for ep_id in PRICING_TABLE},
        methodology=dict(
            relevance_prompt=RELEVANCE_PROMPT,
            newsworthiness_prompt=NEWSWORTHINESS_PROMPT,
        ),
        judges=[
            {"name": "Anthropic", "model": ClaudeJudge.model_name},
            {"name": "OpenAI",    "model": OpenAIJudge.model_name},
        ],
    )
