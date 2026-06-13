from __future__ import annotations

from datetime import datetime, timezone

import httpx

from eval_search.models import SearchResult, TopicCategory
from eval_search.providers.base import EndpointVariant, SearchProvider


class TavilySearchProvider(SearchProvider):
    provider_id = "tavily"
    display_name = "Tavily"
    endpoints = [
        EndpointVariant(
            endpoint_id="tavily_news",
            display_name="Tavily News",
            description="News topic mode - NOTE: no publication dates returned",
            supports_news_category=True,
        ),
        EndpointVariant(
            endpoint_id="tavily_general",
            display_name="Tavily General (Advanced)",
            description="General search with advanced depth - NOTE: no publication dates returned",
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
        time_range = "week" if lookback_days <= 7 else "month"

        if endpoint_id == "tavily_news":
            payload: dict = {
                "query": query,
                "topic": "news",
                "search_depth": "basic",
                "max_results": max_results,
                "time_range": time_range,
            }
        elif endpoint_id == "tavily_general":
            payload = {
                "query": query,
                "topic": "general",
                "search_depth": "advanced",
                "max_results": max_results,
            }
        else:
            raise ValueError(f"Unknown endpoint: {endpoint_id}")

        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        response = await client.post("https://api.tavily.com/search", json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()

        fetched_at = datetime.now(timezone.utc)
        results = []

        for item in data.get("results", []):
            results.append(
                SearchResult(
                    provider_id="tavily",
                    endpoint_id=endpoint_id,
                    query=query,
                    topic_category=topic_category,
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    snippet=item.get("content"),
                    # Tavily does not return publication dates
                    published_date=None,
                    raw_date_str=None,
                    provider_score=item.get("score"),
                    fetched_at=fetched_at,
                )
            )

        return results, 0.0
