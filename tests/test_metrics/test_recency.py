from datetime import datetime, timedelta, timezone

import pytest

from eval_search.metrics.recency import parse_date, score_recency

FETCHED_AT = datetime(2025, 6, 13, 12, 0, 0, tzinfo=timezone.utc)


def _pub(hours_ago: float) -> datetime:
    return FETCHED_AT - timedelta(hours=hours_ago)


def test_score_none_date_returns_zero():
    score, age = score_recency(None, 7, FETCHED_AT)
    assert score == 0.0
    assert age is None


def test_score_within_24h_is_one():
    score, age = score_recency(_pub(12), 7, FETCHED_AT)
    assert score == 1.0
    assert age == pytest.approx(12.0, rel=1e-3)


def test_score_at_24h_boundary():
    score, _ = score_recency(_pub(24), 7, FETCHED_AT)
    assert score == 1.0


def test_score_within_3d():
    score, _ = score_recency(_pub(48), 7, FETCHED_AT)
    assert 0.85 <= score <= 1.0


def test_score_3_to_7d():
    score, _ = score_recency(_pub(5 * 24), 7, FETCHED_AT)
    assert 0.65 <= score <= 0.85


def test_score_7_to_14d():
    score, _ = score_recency(_pub(10 * 24), 7, FETCHED_AT)
    assert 0.35 <= score <= 0.65


def test_score_14_to_30d():
    score, _ = score_recency(_pub(20 * 24), 7, FETCHED_AT)
    assert 0.15 <= score <= 0.35


def test_score_older_than_30d_is_zero():
    score, _ = score_recency(_pub(31 * 24), 7, FETCHED_AT)
    assert score == 0.0


def test_parse_iso8601():
    dt = parse_date("2025-06-10T08:00:00Z")
    assert dt is not None
    assert dt.year == 2025
    assert dt.tzinfo is not None


def test_parse_relative_string():
    dt = parse_date("3 hours ago")
    assert dt is not None


def test_parse_none_returns_none():
    assert parse_date(None) is None


def test_parse_empty_returns_none():
    assert parse_date("") is None


def test_future_dated_article_scores_one():
    future = FETCHED_AT + timedelta(hours=2)
    score, age = score_recency(future, 7, FETCHED_AT)
    assert score == 1.0
    assert age == 0.0
