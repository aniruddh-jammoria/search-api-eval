from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class TopicCategory(str, Enum):
    AI = "ai"
    TECHNOLOGY = "technology"
    FINANCE = "finance"
    ENTERTAINMENT = "entertainment"
    MUSIC = "music"
    SPORTS = "sports"
    SCIENCE = "science"
    POLITICS = "politics"
    INVESTING = "investing"
    HEALTH = "health"
    BUSINESS = "business"


class SearchResult(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    provider_id: str
    endpoint_id: str
    query: str
    topic_category: TopicCategory
    title: str
    url: str
    snippet: str | None = None       # raw provider snippet / meta description
    summary: str | None = None       # LLM-generated summary of fetched page content
    published_date: datetime | None = None
    raw_date_str: str | None = None
    provider_score: float | None = None
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class JudgeScore(BaseModel):
    judge_id: str
    relevance: int | None = None       # 1-5, None if parse failed
    newsworthiness: int | None = None
    reasoning: str = ""
    raw_response: str = ""
    cost_usd: float = 0.0              # actual API cost for this judge call


class EvaluatedResult(BaseModel):
    result: SearchResult
    recency_score: float = 0.0
    recency_age_hours: float | None = None
    judge_scores: list[JudgeScore] = Field(default_factory=list)
    summary_cost_usd: float = 0.0


class ProviderEndpointResult(BaseModel):
    provider_id: str
    endpoint_id: str
    topic_category: TopicCategory
    query: str
    latency_ms: float = 0.0
    estimated_cost_usd: float = 0.0
    raw_count: int = 0
    results: list[EvaluatedResult] = Field(default_factory=list)
    error: str | None = None


class EvaluationRun(BaseModel):
    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    lookback_days: int
    topics: list[TopicCategory]
    providers_tested: list[str]
    queries_per_topic: int
    endpoint_results: list[ProviderEndpointResult] = Field(default_factory=list)


class AggregatedMetrics(BaseModel):
    provider_id: str
    endpoint_id: str
    topic_category: TopicCategory | None = None
    # Recency
    avg_recency_score: float = 0.0
    pct_within_lookback: float = 0.0
    median_age_hours: float | None = None
    # Relevance
    avg_relevance_claude: float | None = None
    avg_relevance_openai: float | None = None
    judge_relevance_correlation: float | None = None
    # Newsworthiness
    avg_newsworthiness_claude: float | None = None
    avg_newsworthiness_openai: float | None = None
    # Cost
    search_cost_usd: float = 0.0
    summarization_cost_usd: float = 0.0   # Claude Haiku per-page summaries (product cost)
    judge_cost_usd: float = 0.0            # LLM judge calls (eval framework cost, not product)
    total_cost_usd: float = 0.0
    cost_per_relevant_article: float | None = None
    # Latency
    p50_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
