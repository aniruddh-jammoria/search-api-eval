from __future__ import annotations

import plotly.graph_objects as go

from eval_search.models import AggregatedMetrics, EvaluatedResult, ProviderEndpointResult


def _endpoint_label(m: AggregatedMetrics) -> str:
    return m.endpoint_id.replace("_", " ")


def recency_stacked_bar(
    endpoint_results: list[ProviderEndpointResult],
) -> go.Figure:
    """Stacked bar: % of results in each age bucket per endpoint."""
    buckets = ["< 1 day", "1–3 days", "3–7 days", "> 7 days", "Unknown"]
    colors = ["#2ecc71", "#f39c12", "#e67e22", "#e74c3c", "#95a5a6"]

    endpoints: list[str] = []
    counts: dict[str, list[float]] = {b: [] for b in buckets}

    seen: set[str] = set()
    for ep in endpoint_results:
        if ep.error or ep.endpoint_id in seen:
            continue
        seen.add(ep.endpoint_id)
        endpoints.append(ep.endpoint_id.replace("_", " "))

        ages = [ev.recency_age_hours for ev in ep.results]
        total = len(ages) or 1
        b0 = sum(1 for a in ages if a is not None and a <= 24) / total * 100
        b1 = sum(1 for a in ages if a is not None and 24 < a <= 72) / total * 100
        b2 = sum(1 for a in ages if a is not None and 72 < a <= 168) / total * 100
        b3 = sum(1 for a in ages if a is not None and a > 168) / total * 100
        b4 = sum(1 for a in ages if a is None) / total * 100

        for bucket, val in zip(buckets, [b0, b1, b2, b3, b4]):
            counts[bucket].append(val)

    fig = go.Figure()
    for bucket, color in zip(buckets, colors):
        fig.add_trace(go.Bar(name=bucket, x=endpoints, y=counts[bucket], marker_color=color))

    fig.update_layout(
        barmode="stack",
        title="Recency Distribution by Endpoint",
        xaxis_title="Endpoint",
        yaxis_title="% of Results",
        yaxis=dict(range=[0, 100]),
        legend_title="Age bucket",
        height=400,
    )
    return fig


def age_box_plot(endpoint_results: list[ProviderEndpointResult]) -> go.Figure:
    """Box plot of result age (hours) per endpoint."""
    fig = go.Figure()
    seen: set[str] = set()
    for ep in endpoint_results:
        if ep.error or ep.endpoint_id in seen:
            continue
        seen.add(ep.endpoint_id)
        ages = [ev.recency_age_hours for ev in ep.results if ev.recency_age_hours is not None]
        if ages:
            fig.add_trace(go.Box(y=ages, name=ep.endpoint_id.replace("_", " "), boxpoints="outliers"))

    fig.update_layout(
        title="Result Age Distribution (hours)",
        yaxis_title="Age (hours)",
        height=400,
    )
    return fig


def _score_heatmap(
    metrics: list[AggregatedMetrics],
    field: str,
    title: str,
) -> go.Figure:
    endpoints = sorted({m.endpoint_id for m in metrics if m.topic_category})
    topics = sorted({m.topic_category.value for m in metrics if m.topic_category})

    z: list[list[float | None]] = []
    for ep in endpoints:
        row: list[float | None] = []
        for t in topics:
            match = next(
                (m for m in metrics if m.endpoint_id == ep and m.topic_category and m.topic_category.value == t),
                None,
            )
            row.append(getattr(match, field, None) if match else None)
        z.append(row)

    fig = go.Figure(
        go.Heatmap(
            z=z,
            x=topics,
            y=[e.replace("_", " ") for e in endpoints],
            colorscale="RdYlGn",
            zmin=1,
            zmax=5,
            colorbar=dict(title="Score"),
            text=[[f"{v:.2f}" if v else "N/A" for v in row] for row in z],
            texttemplate="%{text}",
        )
    )
    fig.update_layout(
        title=title,
        xaxis_title="Topic",
        yaxis_title="Endpoint",
        height=max(300, len(endpoints) * 40 + 100),
    )
    return fig


def relevance_heatmap(metrics: list[AggregatedMetrics], judge_id: str) -> go.Figure:
    field = "avg_relevance_claude" if judge_id == "claude_haiku" else "avg_relevance_openai"
    label = "Claude Haiku" if judge_id == "claude_haiku" else "GPT-4o-mini"
    return _score_heatmap(metrics, field, f"Relevance — {label}")


def newsworthiness_heatmap(metrics: list[AggregatedMetrics], judge_id: str) -> go.Figure:
    field = "avg_newsworthiness_claude" if judge_id == "claude_haiku" else "avg_newsworthiness_openai"
    label = "Claude Haiku" if judge_id == "claude_haiku" else "GPT-4o-mini"
    return _score_heatmap(metrics, field, f"Newsworthiness — {label}")


def judge_correlation_scatter(evaluated_results: list[EvaluatedResult]) -> go.Figure:
    """Scatter: Claude relevance vs OpenAI relevance, one point per result."""
    import numpy as np

    claude_scores: list[int] = []
    openai_scores: list[int] = []
    topics: list[str] = []

    for ev in evaluated_results:
        c = next((s.relevance for s in ev.judge_scores if s.judge_id == "claude_haiku" and s.relevance), None)
        o = next((s.relevance for s in ev.judge_scores if s.judge_id == "gpt4o_mini" and s.relevance), None)
        if c is not None and o is not None:
            claude_scores.append(c)
            openai_scores.append(o)
            topics.append(ev.result.topic_category.value)

    annotation = ""
    if len(claude_scores) >= 3:
        r = float(np.corrcoef(claude_scores, openai_scores)[0, 1])
        annotation = f"Pearson r = {r:.3f}"

    fig = go.Figure(
        go.Scatter(
            x=claude_scores,
            y=openai_scores,
            mode="markers",
            marker=dict(opacity=0.6, size=6),
            text=topics,
            hovertemplate="Claude: %{x}<br>OpenAI: %{y}<br>Topic: %{text}",
        )
    )
    # Identity line
    fig.add_shape(type="line", x0=1, y0=1, x1=5, y1=5, line=dict(dash="dash", color="grey"))

    if annotation:
        fig.add_annotation(x=1.2, y=4.8, text=annotation, showarrow=False, font=dict(size=14))

    fig.update_layout(
        title="Judge Agreement: Claude vs OpenAI Relevance",
        xaxis=dict(title="Claude Haiku score", range=[0.5, 5.5]),
        yaxis=dict(title="GPT-4o-mini score", range=[0.5, 5.5]),
        height=400,
    )
    return fig



def cost_bar(metrics: list[AggregatedMetrics]) -> go.Figure:
    """Stacked bar: Search / Summarization / Judge cost per endpoint."""
    summary: dict[str, dict[str, float]] = {}
    for m in metrics:
        if m.endpoint_id not in summary:
            summary[m.endpoint_id] = {"search": 0.0, "summarization": 0.0, "judge": 0.0}
        summary[m.endpoint_id]["search"] += m.search_cost_usd
        summary[m.endpoint_id]["summarization"] += m.summarization_cost_usd
        summary[m.endpoint_id]["judge"] += m.judge_cost_usd

    labels = [k.replace("_", " ") for k in summary]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="Search", x=labels,
        y=[summary[k]["search"] for k in summary],
        marker_color="#3498db",
    ))
    fig.add_trace(go.Bar(
        name="Summarization (product)", x=labels,
        y=[summary[k]["summarization"] for k in summary],
        marker_color="#2ecc71",
    ))
    fig.add_trace(go.Bar(
        name="Judge (eval only)", x=labels,
        y=[summary[k]["judge"] for k in summary],
        marker_color="#e67e22",
    ))

    fig.update_layout(
        barmode="stack",
        title="Cost Breakdown by Component",
        xaxis_title="Endpoint",
        yaxis_title="USD",
        height=400,
    )
    return fig


def latency_box_plot(endpoint_results: list[ProviderEndpointResult]) -> go.Figure:
    """Box plot of call latency per endpoint."""
    from collections import defaultdict

    latencies: dict[str, list[float]] = defaultdict(list)
    for ep in endpoint_results:
        if not ep.error and ep.latency_ms > 0:
            latencies[ep.endpoint_id].append(ep.latency_ms)

    fig = go.Figure()
    for ep_id, vals in sorted(latencies.items()):
        fig.add_trace(go.Box(y=vals, name=ep_id.replace("_", " "), boxpoints="outliers"))

    fig.update_layout(
        title="Latency Distribution per Endpoint (ms)",
        yaxis_title="Latency (ms)",
        height=400,
    )
    return fig
