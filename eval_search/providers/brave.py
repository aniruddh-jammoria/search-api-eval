from __future__ import annotations

from datetime import datetime, timezone

import httpx

from eval_search.metrics.recency import parse_date
from eval_search.models import SearchResult, TopicCategory
from eval_search.providers.base import EndpointVariant, SearchProvider


class BraveSearchProvider(SearchProvider):
    provider_id = "brave"
    display_name = "BraveSearch"
    endpoints = [
        EndpointVariant(
            endpoint_id="brave_web",
            display_name="Brave Web Search",
            description="General web search with freshness filter",
            supports_date_filter=True,
        ),
        EndpointVariant(
            endpoint_id="brave_news",
            display_name="Brave News Search",
            description="News-specific index with freshness filter",
            supports_date_filter=True,
            supports_news_category=True,
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
        freshness = "pw" if lookback_days <= 7 else "pm"

        if endpoint_id == "brave_web":
            url = "https://api.search.brave.com/res/v1/web/search"
            params: dict = {"q": query, "count": min(max_results, 20), "freshness": freshness}
        elif endpoint_id == "brave_news":
            url = "https://api.search.brave.com/res/v1/news/search"
            params = {"q": query, "count": min(max_results, 20), "freshness": freshness}
        else:
            raise ValueError(f"Unknown endpoint: {endpoint_id}")

        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": self._api_key,
        }
        response = await client.get(url, params=params, headers=headers)
        response.raise_for_status()
        data = response.json()

        fetched_at = datetime.now(timezone.utc)
        items = (
            data.get("results", [])
            if endpoint_id == "brave_news"
            else data.get("web", {}).get("results", [])
        )

        results = []
        for item in items:
            raw_date = item.get("page_age") or item.get("age")
            snippet = item.get("description")
            if not snippet and item.get("extra_snippets"):
                snippet = item["extra_snippets"][0]
            results.append(
                SearchResult(
                    provider_id="brave",
                    endpoint_id=endpoint_id,
                    query=query,
                    topic_category=topic_category,
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    snippet=snippet,
                    published_date=parse_date(raw_date, "brave"),
                    raw_date_str=raw_date,
                    provider_score=item.get("score"),
                    fetched_at=fetched_at,
                )
            )

        return results, 0.0
