from __future__ import annotations

from datetime import datetime, timezone

import httpx

from eval_search.metrics.recency import parse_date
from eval_search.models import SearchResult, TopicCategory
from eval_search.providers.base import EndpointVariant, SearchProvider


class SerpApiProvider(SearchProvider):
    provider_id = "serpapi"
    display_name = "SerpApi"
    endpoints = [
        EndpointVariant(
            endpoint_id="serpapi_google_news",
            display_name="SerpApi Google News",
            description="Google News via SerpApi (engine=google_news)",
            supports_date_filter=True,
            supports_news_category=True,
        ),
        EndpointVariant(
            endpoint_id="serpapi_google_search",
            display_name="SerpApi Google Search (news filter)",
            description="Google web search with news tab via SerpApi",
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
        tbs = "qdr:w" if lookback_days <= 7 else "qdr:m"

        if endpoint_id == "serpapi_google_news":
            params: dict = {
                "engine": "google_news",
                "q": query,
                "api_key": self._api_key,
                "num": max_results,
            }
            result_key = "news_results"
        elif endpoint_id == "serpapi_google_search":
            params = {
                "engine": "google",
                "q": query,
                "tbm": "nws",
                "tbs": tbs,
                "api_key": self._api_key,
                "num": max_results,
            }
            result_key = "news_results"
        else:
            raise ValueError(f"Unknown endpoint: {endpoint_id}")

        response = await client.get("https://serpapi.com/search", params=params)
        response.raise_for_status()
        data = response.json()

        fetched_at = datetime.now(timezone.utc)
        results = []

        for item in data.get(result_key, []):
            raw_date = item.get("published_at") or item.get("date")
            results.append(
                SearchResult(
                    provider_id="serpapi",
                    endpoint_id=endpoint_id,
                    query=query,
                    topic_category=topic_category,
                    title=item.get("title", ""),
                    url=item.get("link", ""),
                    snippet=item.get("snippet") or (item.get("source") or {}).get("name"),
                    published_date=parse_date(raw_date, "serpapi"),
                    raw_date_str=raw_date,
                    provider_score=None,
                    fetched_at=fetched_at,
                )
            )

        return results, 0.0
