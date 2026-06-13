from __future__ import annotations

from datetime import datetime, timezone

import dateparser


def parse_date(raw: str | None, provider_id: str = "") -> datetime | None:
    """Parse a date string from any provider into a UTC datetime."""
    if not raw:
        return None

    # Try ISO 8601 first (fastest path)
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
    except (ValueError, AttributeError):
        pass

    # Fall back to dateparser — handles relative strings ("3 hours ago", "2 days ago")
    parsed = dateparser.parse(
        raw,
        settings={"RETURN_AS_TIMEZONE_AWARE": True, "PREFER_DAY_OF_MONTH": "first"},
    )
    if parsed:
        return parsed.astimezone(timezone.utc)

    return None


def score_recency(
    published_date: datetime | None,
    lookback_days: int,
    fetched_at: datetime,
) -> tuple[float, float | None]:
    """
    Returns (score 0.0–1.0, age_hours or None).

    Piecewise linear curve over age_hours:
      ≤ 24 h        → 1.00
      24–72 h       → 0.85–1.00
      3–7 d         → 0.65–0.85
      7–14 d        → 0.35–0.65
      14–30 d       → 0.15–0.35
      > 30 d | None → 0.00
    """
    if published_date is None:
        return 0.0, None

    fetched_utc = (
        fetched_at.replace(tzinfo=timezone.utc)
        if fetched_at.tzinfo is None
        else fetched_at.astimezone(timezone.utc)
    )
    age_hours = max(0.0, (fetched_utc - published_date).total_seconds() / 3600)

    if age_hours <= 24:
        score = 1.0
    elif age_hours <= 72:
        score = 1.0 - (age_hours - 24) / (72 - 24) * (1.0 - 0.85)
    elif age_hours <= 7 * 24:
        score = 0.85 - (age_hours - 72) / (7 * 24 - 72) * (0.85 - 0.65)
    elif age_hours <= 14 * 24:
        score = 0.65 - (age_hours - 7 * 24) / (7 * 24) * (0.65 - 0.35)
    elif age_hours <= 30 * 24:
        score = 0.35 - (age_hours - 14 * 24) / (16 * 24) * (0.35 - 0.15)
    else:
        score = 0.0

    return round(score, 4), round(age_hours, 2)
