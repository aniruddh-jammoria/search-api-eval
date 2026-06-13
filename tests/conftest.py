from datetime import datetime, timezone
import pytest
from eval_search.models import SearchResult, TopicCategory


@pytest.fixture
def base_result() -> SearchResult:
    return SearchResult(
        provider_id="test",
        endpoint_id="test_endpoint",
        query="test query",
        topic_category=TopicCategory.TECHNOLOGY,
        title="Test Article",
        url="https://example.com/article",
        snippet="This is a test snippet.",
        fetched_at=datetime(2025, 6, 13, 12, 0, 0, tzinfo=timezone.utc),
    )
