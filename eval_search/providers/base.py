from __future__ import annotations

from abc import ABC, abstractmethod

import httpx
from pydantic import BaseModel

from eval_search.models import SearchResult, TopicCategory


class EndpointVariant(BaseModel):
    endpoint_id: str
    display_name: str
    description: str
    supports_date_filter: bool = False
    supports_news_category: bool = False
    # When True, Phase 2 uses the provider-supplied snippet as the summary
    # instead of fetching the page and calling an LLM.
    skip_summarization: bool = False


class SearchProvider(ABC):
    provider_id: str
    display_name: str
    endpoints: list[EndpointVariant]

    @abstractmethod
    async def search(
        self,
        query: str,
        endpoint_id: str,
        lookback_days: int,
        max_results: int,
        client: httpx.AsyncClient,
        topic_category: TopicCategory = TopicCategory.TECHNOLOGY,
    ) -> tuple[list[SearchResult], float]:
        """
        Fetch results for the given query and endpoint.
        Returns (results, api_reported_cost_usd).
        Cost is 0.0 if the provider does not report it in the response.
        """
        ...

    def estimate_cost(self, endpoint_id: str, num_calls: int = 1) -> float:
        from eval_search.metrics.cost import estimate_cost
        return estimate_cost(endpoint_id, num_calls)

    def get_endpoint(self, endpoint_id: str) -> EndpointVariant:
        for ep in self.endpoints:
            if ep.endpoint_id == endpoint_id:
                return ep
        raise ValueError(f"Unknown endpoint '{endpoint_id}' for provider '{self.provider_id}'")
