from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ProviderPricing(BaseModel):
    cost_per_call: float | None  # None = read cost from API response
    unit: str                     # "per_request" | "per_credit" | "from_response"
    credits_per_call: int = 1


PRICING_TABLE: dict[str, ProviderPricing] = {
    "brave_web":              ProviderPricing(cost_per_call=0.005,  unit="per_request"),
    "brave_news":             ProviderPricing(cost_per_call=0.005,  unit="per_request"),
    "exa_auto":               ProviderPricing(cost_per_call=None,   unit="from_response"),
    "exa_neural":             ProviderPricing(cost_per_call=None,   unit="from_response"),
    "exa_keyword":            ProviderPricing(cost_per_call=None,   unit="from_response"),
    "tavily_news":            ProviderPricing(cost_per_call=0.001,  unit="per_credit", credits_per_call=1),
    "tavily_general":         ProviderPricing(cost_per_call=0.001,  unit="per_credit", credits_per_call=2),
    "serper_search":          ProviderPricing(cost_per_call=0.001,  unit="per_request"),
    "serper_news":            ProviderPricing(cost_per_call=0.001,  unit="per_request"),
    "serpapi_google_news":    ProviderPricing(cost_per_call=0.025,  unit="per_request"),
    "serpapi_google_search":  ProviderPricing(cost_per_call=0.025,  unit="per_request"),
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Search provider API keys
    brave_api_key: str = ""
    exa_api_key: str = ""
    tavily_api_key: str = ""
    serper_api_key: str = ""
    serpapi_api_key: str = ""

    # LLM judge API keys
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    # Evaluation parameters
    lookback_days: int = 7
    max_results_per_query: int = 10
    queries_per_topic: int = 3

    # Concurrency
    provider_concurrency: int = 4
    judge_concurrency: int = 8

    # Judge prompt overrides (None = use built-in defaults)
    relevance_prompt_override: str | None = None
    newsworthiness_prompt_override: str | None = None

    # Output
    output_dir: Path = Path("./reports")
    save_raw_json: bool = True

    @field_validator(
        "brave_api_key", "exa_api_key", "tavily_api_key",
        "serper_api_key", "serpapi_api_key",
        "anthropic_api_key", "openai_api_key",
        mode="before",
    )
    @classmethod
    def _strip_key(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v
