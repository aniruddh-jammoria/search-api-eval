from __future__ import annotations

from datetime import datetime, timezone

import httpx

from eval_search.metrics.recency import parse_date
from eval_search.models import SearchResult, TopicCategory
from eval_search.providers.base import EndpointVariant, SearchProvider


class SerperSearchProvider(SearchProvider):
    provider_id = "serper"
    display_name = "Serper"
    endpoints = [
        EndpointVariant(
            endpoint_id="serper_search",
            display_name="Serper Web Search",
            description="Google web results via Serper with time filter",
            supports_date_filter=True,
        ),
        EndpointVariant(
            endpoint_id="serper_news",
            display_name="Serper Google News",
            description="Google News via Serper with past-week filter",
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
        tbs = "qdr:w" if lookback_days <= 7 else "qdr:m"

        if endpoint_id == "serper_search":
            url = "https://google.serper.dev/search"
            result_key = "organic"
        elif endpoint_id == "serper_news":
            url = "https://google.serper.dev/news"
            result_key = "news"
        else:
            raise ValueError(f"Unknown endpoint: {endpoint_id}")

        payload = {"q": query, "num": max_results, "tbs": tbs}
        headers = {"X-API-KEY": self._api_key, "Content-Type": "application/json"}
        response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()

        fetched_at = datetime.now(timezone.utc)
        results = []

        for item in data.get(result_key, []):
            raw_date = item.get("date")
            results.append(
                SearchResult(
                    provider_id="serper",
                    endpoint_id=endpoint_id,
                    query=query,
                    topic_category=topic_category,
                    title=item.get("title", ""),
                    url=item.get("link", ""),
                    snippet=item.get("snippet"),
                    published_date=parse_date(raw_date, "serper"),
                    raw_date_str=raw_date,
                    provider_score=None,
                    fetched_at=fetched_at,
                )
            )

        return results, 0.0
