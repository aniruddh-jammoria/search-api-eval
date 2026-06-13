from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx

from eval_search.metrics.recency import parse_date
from eval_search.models import SearchResult, TopicCategory
from eval_search.providers.base import EndpointVariant, SearchProvider

# Endpoints that should request highlights from Exa
_HIGHLIGHTS_ENDPOINTS = {"exa_auto", "exa_auto_native", "exa_neural", "exa_keyword"}


class ExaSearchProvider(SearchProvider):
    provider_id = "exa"
    display_name = "Exa"
    endpoints = [
        EndpointVariant(
            endpoint_id="exa_auto_native",
            display_name="Exa Auto — Native Content",
            description="Exa highlights used directly as summary (content cost baked into search cost)",
            supports_date_filter=True,
            supports_news_category=True,
            skip_summarization=True,
        ),
        EndpointVariant(
            endpoint_id="exa_auto_fetch",
            display_name="Exa Auto — Fetch + Summarize",
            description="Exa search only (no highlights), page fetched and summarized with Claude Haiku",
            supports_date_filter=True,
            supports_news_category=True,
            skip_summarization=False,
        ),
        EndpointVariant(
            endpoint_id="exa_auto",
            display_name="Exa Auto (News)",
            description="Auto search type with news category filter",
            supports_date_filter=True,
            supports_news_category=True,
        ),
        EndpointVariant(
            endpoint_id="exa_neural",
            display_name="Exa Neural (News)",
            description="Neural semantic search with news category filter",
            supports_date_filter=True,
            supports_news_category=True,
        ),
        EndpointVariant(
            endpoint_id="exa_keyword",
            display_name="Exa Keyword",
            description="Keyword search without news category",
            supports_date_filter=True,
        ),
    ]

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def search(
        self,
        query: str,
        endpoint_id: str,
        lookback_days: int,
        max_results: int,
        client: httpx.AsyncClient,
        topic_category: TopicCategory = TopicCategory.TECHNOLOGY,
    ) -> tuple[list[SearchResult], float]:
        start_date = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )

        payload: dict = {
            "query": query,
            "numResults": max_results,
            "startPublishedDate": start_date,
        }

        # Request highlights only when the endpoint uses them.
        # exa_auto_fetch deliberately omits contents to avoid paying for
        # highlights we won't use (page is fetched + summarized separately).
        if endpoint_id in _HIGHLIGHTS_ENDPOINTS:
            payload["contents"] = {"highlights": {"numSentences": 3}}

        base_id = endpoint_id.replace("_native", "").replace("_fetch", "")
        if base_id in ("exa_auto", "exa_auto_native", "exa_auto_fetch"):
            payload["type"] = "auto"
            payload["category"] = "news"
        elif endpoint_id == "exa_neural":
            payload["type"] = "neural"
            payload["category"] = "news"
        elif endpoint_id == "exa_keyword":
            payload["type"] = "keyword"
        else:
            raise ValueError(f"Unknown endpoint: {endpoint_id}")

        headers = {"x-api-key": self._api_key, "Content-Type": "application/json"}
        response = await client.post("https://api.exa.ai/search", json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()

        api_cost = data.get("costDollars", {}).get("total", 0.0)
        fetched_at = datetime.now(timezone.utc)
        results = []

        for item in data.get("results", []):
            highlights = item.get("highlights") or []
            snippet = " ".join(highlights) if highlights else None

            results.append(
                SearchResult(
                    provider_id="exa",
                    endpoint_id=endpoint_id,
                    query=query,
                    topic_category=topic_category,
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    snippet=snippet,
                    published_date=parse_date(item.get("publishedDate"), "exa"),
                    raw_date_str=item.get("publishedDate"),
                    provider_score=item.get("score"),
                    fetched_at=fetched_at,
                )
            )

        return results, api_cost
