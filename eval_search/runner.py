from __future__ import annotations

import asyncio
import logging
import statistics
from collections import defaultdict

import numpy as np
import httpx
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn

from anthropic import AsyncAnthropic

from eval_search.config import Settings
from eval_search.content.fetcher import fetch_page_text
from eval_search.content.summarizer import summarize as summarize_article
from eval_search.judges.base import LLMJudge
from eval_search.judges.claude_judge import ClaudeJudge
from eval_search.judges.openai_judge import OpenAIJudge
from eval_search.metrics.cost import cost_per_relevant_article, estimate_cost
from eval_search.metrics.latency import measure_latency
from eval_search.metrics.recency import score_recency
from eval_search.models import (
    AggregatedMetrics,
    EvaluatedResult,
    EvaluationRun,
    ProviderEndpointResult,
    SearchResult,
    TopicCategory,
)
from eval_search.providers.base import EndpointVariant, SearchProvider
from eval_search.providers.brave import BraveSearchProvider
from eval_search.providers.exa import ExaSearchProvider
from eval_search.providers.serpapi import SerpApiProvider
from eval_search.providers.serper import SerperSearchProvider
from eval_search.providers.tavily import TavilySearchProvider
from eval_search.queries.bank import get_queries

console = Console()
logger = logging.getLogger(__name__)

PROVIDER_FACTORY: dict[str, type[SearchProvider]] = {
    "brave": BraveSearchProvider,
    "exa": ExaSearchProvider,
    "tavily": TavilySearchProvider,
    "serper": SerperSearchProvider,
    "serpapi": SerpApiProvider,
}

PROVIDER_KEY_MAP: dict[str, str] = {
    "brave": "brave_api_key",
    "exa": "exa_api_key",
    "tavily": "tavily_api_key",
    "serper": "serper_api_key",
    "serpapi": "serpapi_api_key",
}


def _build_providers(settings: Settings, provider_ids: list[str]) -> list[SearchProvider]:
    providers = []
    for pid in provider_ids:
        cls = PROVIDER_FACTORY.get(pid)
        if cls is None:
            logger.warning("Unknown provider '%s' — skipping", pid)
            continue
        key = getattr(settings, PROVIDER_KEY_MAP[pid], "")
        providers.append(cls(key))
    return providers


def _build_judges(settings: Settings, judge_ids: list[str]) -> list[LLMJudge]:
    rel  = getattr(settings, "relevance_prompt_override", None) or None
    news = getattr(settings, "newsworthiness_prompt_override", None) or None
    judges: list[LLMJudge] = []
    if "claude" in judge_ids and settings.anthropic_api_key:
        judges.append(ClaudeJudge(settings.anthropic_api_key, rel, news))
    if "openai" in judge_ids and settings.openai_api_key:
        judges.append(OpenAIJudge(settings.openai_api_key, rel, news))
    return judges


async def run_evaluation(
    settings: Settings,
    topics: list[TopicCategory],
    provider_ids: list[str],
    endpoint_ids: list[str] | None,
    judge_ids: list[str],
) -> tuple[EvaluationRun, list[AggregatedMetrics]]:
    providers = _build_providers(settings, provider_ids)
    judges = _build_judges(settings, judge_ids)

    # Build (provider, endpoint) work list
    work: list[tuple[SearchProvider, object]] = []
    for provider in providers:
        for endpoint in provider.endpoints:
            if endpoint_ids is None or endpoint.endpoint_id in endpoint_ids:
                work.append((provider, endpoint))

    # Only list providers that actually have endpoints in the work list
    actual_provider_ids = list(dict.fromkeys(p.provider_id for p, _ in work))

    run = EvaluationRun(
        lookback_days=settings.lookback_days,
        topics=topics,
        providers_tested=actual_provider_ids,
        queries_per_topic=settings.queries_per_topic,
    )

    # ── Phase 1: Fetch ────────────────────────────────────────────────────────
    sem = asyncio.Semaphore(settings.provider_concurrency)
    total_calls = len(work) * len(topics) * settings.queries_per_topic

    async def fetch_one(
        provider: SearchProvider,
        endpoint,
        topic: TopicCategory,
        query: str,
        progress: Progress,
        task_id,
    ) -> ProviderEndpointResult:
        async with sem:
            try:
                async with measure_latency() as cap:
                    results, api_cost = await provider.search(
                        query=query,
                        endpoint_id=endpoint.endpoint_id,
                        lookback_days=settings.lookback_days,
                        max_results=settings.max_results_per_query,
                        client=client,
                        topic_category=topic,
                    )

                cost = api_cost if api_cost > 0 else estimate_cost(endpoint.endpoint_id)

                evaluated = [
                    EvaluatedResult(
                        result=r,
                        recency_score=score_recency(r.published_date, settings.lookback_days, r.fetched_at)[0],
                        recency_age_hours=score_recency(r.published_date, settings.lookback_days, r.fetched_at)[1],
                    )
                    for r in results
                ]
                return ProviderEndpointResult(
                    provider_id=provider.provider_id,
                    endpoint_id=endpoint.endpoint_id,
                    topic_category=topic,
                    query=query,
                    latency_ms=cap.ms,
                    estimated_cost_usd=cost,
                    raw_count=len(results),
                    results=evaluated,
                )
            except Exception as e:
                logger.error(
                    "Fetch failed [%s/%s] topic=%s query='%s': %s",
                    provider.provider_id, endpoint.endpoint_id, topic.value, query, e,
                )
                return ProviderEndpointResult(
                    provider_id=provider.provider_id,
                    endpoint_id=endpoint.endpoint_id,
                    topic_category=topic,
                    query=query,
                    error=str(e),
                )
            finally:
                progress.advance(task_id)

    all_endpoint_results: list[ProviderEndpointResult] = []

    async with httpx.AsyncClient(timeout=30.0) as client:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task_id = progress.add_task("[cyan]Phase 1/4  Fetching results...", total=total_calls)

            coros = [
                fetch_one(provider, endpoint, topic, query, progress, task_id)
                for provider, endpoint in work
                for topic in topics
                for query in get_queries(topic, settings.queries_per_topic)
            ]
            all_endpoint_results = list(await asyncio.gather(*coros))

    # ── Phase 2: Summarize ────────────────────────────────────────────────────
    # Build a lookup so we know which endpoints skip LLM summarization.
    ep_lookup: dict[str, EndpointVariant] = {ep.endpoint_id: ep for _, ep in work}

    all_evs = [
        ev
        for ep in all_endpoint_results if not ep.error
        for ev in ep.results
    ]

    # Results whose endpoint provides content natively — use the snippet directly.
    for ev in all_evs:
        ep_var = ep_lookup.get(ev.result.endpoint_id)
        if ep_var and ep_var.skip_summarization:
            ev.result.summary = ev.result.snippet or ""
            ev.summary_cost_usd = 0.0

    # For the rest, deduplicate by URL and fetch + LLM-summarize.
    fetch_evs = [
        ev for ev in all_evs
        if ev.result.summary is None
    ]
    url_to_ev: dict[str, EvaluatedResult] = {}
    for ev in fetch_evs:
        url_to_ev.setdefault(ev.result.url, ev)
    unique_evs = list(url_to_ev.values())

    console.print(
        f"[cyan]Phase 2/3  Fetching + summarizing {len(unique_evs)} unique pages "
        f"({len(fetch_evs)} results, {len(all_evs) - len(fetch_evs)} using native content)..."
    )

    anthropic_client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    page_sem = asyncio.Semaphore(settings.judge_concurrency)

    async def fetch_and_summarize(ev: EvaluatedResult) -> None:
        async with page_sem:
            async with httpx.AsyncClient(timeout=15.0) as page_client:
                text = await fetch_page_text(ev.result.url, page_client)
            if text:
                summary, cost = await summarize_article(ev.result.title, text, anthropic_client)
            else:
                summary = ev.result.snippet or ""
                cost = 0.0
            ev.result.summary = summary
            ev.summary_cost_usd = cost

    if unique_evs:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task_id = progress.add_task("[cyan]Phase 2/3  Summarizing...", total=len(unique_evs))
            summarize_coros = []
            for ev in unique_evs:
                async def _wrapped(ev=ev):
                    await fetch_and_summarize(ev)
                    progress.advance(task_id)
                summarize_coros.append(_wrapped())
            await asyncio.gather(*summarize_coros)

    # Propagate fetched summaries to duplicate URLs (zero additional cost)
    url_to_summary = {ev.result.url: ev.result.summary for ev in unique_evs}
    for ev in fetch_evs:
        if ev.result.summary is None:
            ev.result.summary = url_to_summary.get(ev.result.url)

    run.endpoint_results = all_endpoint_results

    # ── Phase 3: LLM judging ──────────────────────────────────────────────────
    if judges:
        all_results: list[SearchResult] = [
            ev.result
            for ep in all_endpoint_results
            if not ep.error
            for ev in ep.results
        ]
        result_scores: dict[str, list] = defaultdict(list)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task_id = progress.add_task(
                f"[cyan]Phase 3/3  Judging {len(all_results)} results x {len(judges)} judges...",
                total=len(all_results) * len(judges),
            )
            for judge in judges:
                scores = await judge.judge_batch(all_results, concurrency=settings.judge_concurrency)
                for result, score in zip(all_results, scores):
                    result_scores[result.id].append(score)
                progress.advance(task_id, len(all_results))

        for ep in all_endpoint_results:
            for ev in ep.results:
                ev.judge_scores = result_scores.get(ev.result.id, [])

    console.print("[cyan]Aggregating metrics...")
    metrics = _aggregate_metrics(all_endpoint_results)
    return run, metrics


def _aggregate_metrics(
    endpoint_results: list[ProviderEndpointResult],
) -> list[AggregatedMetrics]:
    grouped: dict[tuple, list[ProviderEndpointResult]] = defaultdict(list)
    for ep in endpoint_results:
        grouped[(ep.provider_id, ep.endpoint_id, ep.topic_category)].append(ep)

    metrics_list: list[AggregatedMetrics] = []

    for (provider_id, endpoint_id, topic_cat), eps in grouped.items():
        evaluated = [ev for ep in eps if not ep.error for ev in ep.results]
        if not evaluated:
            continue

        # Recency
        recency_scores = [ev.recency_score for ev in evaluated]
        avg_recency = statistics.mean(recency_scores)
        pct_within = sum(1 for s in recency_scores if s > 0) / len(recency_scores)
        ages = [ev.recency_age_hours for ev in evaluated if ev.recency_age_hours is not None]
        median_age = statistics.median(ages) if ages else None

        # Judge scores
        def _scores(judge_id: str, field: str) -> list[int]:
            return [
                getattr(s, field)
                for ev in evaluated
                for s in ev.judge_scores
                if s.judge_id == judge_id and getattr(s, field) is not None
            ]

        claude_rel = _scores("claude_haiku", "relevance")
        openai_rel = _scores("gpt4o_mini", "relevance")
        claude_news = _scores("claude_haiku", "newsworthiness")
        openai_news = _scores("gpt4o_mini", "newsworthiness")

        # Pearson correlation between judges on relevance
        corr = None
        if len(claude_rel) >= 3 and len(openai_rel) >= 3:
            n = min(len(claude_rel), len(openai_rel))
            try:
                corr = float(np.corrcoef(claude_rel[:n], openai_rel[:n])[0, 1])
                if np.isnan(corr):
                    corr = None
            except Exception:
                corr = None

        # Cost breakdown
        search_cost        = sum(ep.estimated_cost_usd for ep in eps if not ep.error)
        summarization_cost = sum(ev.summary_cost_usd for ev in evaluated)
        judge_cost         = sum(s.cost_usd for ev in evaluated for s in ev.judge_scores)
        total_cost         = search_cost + summarization_cost + judge_cost

        # Cost per relevant article (avg relevance across both judges ≥ 3)
        avg_rel_per_result: list[float] = []
        for ev in evaluated:
            scores = [s.relevance for s in ev.judge_scores if s.relevance is not None]
            if scores:
                avg_rel_per_result.append(statistics.mean(scores))
        cpr = cost_per_relevant_article(total_cost, avg_rel_per_result)

        # Latency
        latencies = sorted(ep.latency_ms for ep in eps if not ep.error and ep.latency_ms > 0)
        p50 = statistics.median(latencies) if latencies else 0.0
        p95 = latencies[int(len(latencies) * 0.95)] if len(latencies) >= 20 else (latencies[-1] if latencies else 0.0)

        metrics_list.append(
            AggregatedMetrics(
                provider_id=provider_id,
                endpoint_id=endpoint_id,
                topic_category=topic_cat,
                avg_recency_score=round(avg_recency, 4),
                pct_within_lookback=round(pct_within, 4),
                median_age_hours=round(median_age, 2) if median_age is not None else None,
                avg_relevance_claude=round(statistics.mean(claude_rel), 4) if claude_rel else None,
                avg_relevance_openai=round(statistics.mean(openai_rel), 4) if openai_rel else None,
                judge_relevance_correlation=round(corr, 4) if corr is not None else None,
                avg_newsworthiness_claude=round(statistics.mean(claude_news), 4) if claude_news else None,
                avg_newsworthiness_openai=round(statistics.mean(openai_news), 4) if openai_news else None,
                search_cost_usd=round(search_cost, 6),
                summarization_cost_usd=round(summarization_cost, 6),
                judge_cost_usd=round(judge_cost, 6),
                total_cost_usd=round(total_cost, 6),
                cost_per_relevant_article=cpr,
                p50_latency_ms=round(p50, 2),
                p95_latency_ms=round(p95, 2),
            )
        )

    return metrics_list
