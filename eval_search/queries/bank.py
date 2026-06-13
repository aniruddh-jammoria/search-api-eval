from __future__ import annotations

import re
from pathlib import Path

from eval_search.models import TopicCategory

_QUERIES_MD = Path(__file__).parent.parent.parent / "queries.md"

# Maps the lowercase header name from queries.md to a TopicCategory value.
# Extend this if a header name doesn't match the enum value exactly.
_HEADER_TO_TOPIC: dict[str, str] = {
    tc.value: tc.value for tc in TopicCategory
}


def _parse_queries_md(path: Path) -> dict[TopicCategory, list[str]]:
    bank: dict[TopicCategory, list[str]] = {}
    current_topic: TopicCategory | None = None
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return bank

    for line in text.splitlines():
        line = line.strip()
        if line.startswith("## "):
            header = line[3:].strip().lower()
            mapped = _HEADER_TO_TOPIC.get(header)
            try:
                current_topic = TopicCategory(mapped) if mapped else None
            except ValueError:
                current_topic = None
        elif line.startswith("- ") and current_topic is not None:
            query = line[2:].strip()
            if query:
                bank.setdefault(current_topic, []).append(query)

    return bank


def _serialize_query_bank(bank: dict[TopicCategory, list[str]]) -> str:
    lines = [
        "# Search Queries\n",
        "<!-- Format: ## Topic Name followed by bullet list of queries, one per line. -->",
        "<!-- This file is the source of truth for the query bank. Edit here and save from the UI. -->\n",
    ]
    for topic in TopicCategory:
        queries = bank.get(topic, [])
        lines.append(f"## {topic.value.title()}")
        for q in queries:
            lines.append(f"- {q}")
        lines.append("")
    return "\n".join(lines)


try:
    QUERY_BANK: dict[TopicCategory, list[str]] = _parse_queries_md(_QUERIES_MD)
except Exception as _e:
    import logging as _logging
    _logging.getLogger(__name__).warning("Failed to parse %s: %s", _QUERIES_MD, _e)
    QUERY_BANK = {}


def reload_query_bank() -> None:
    """Re-parse queries.md into QUERY_BANK in-place (call after saving edits)."""
    fresh = _parse_queries_md(_QUERIES_MD)
    QUERY_BANK.clear()
    QUERY_BANK.update(fresh)


def save_query_bank(updates: dict[TopicCategory, list[str]]) -> None:
    """Merge updates into QUERY_BANK, write to queries.md, then reload."""
    QUERY_BANK.update(updates)
    _QUERIES_MD.write_text(_serialize_query_bank(QUERY_BANK), encoding="utf-8")
    reload_query_bank()


def get_queries(topic: TopicCategory, n: int) -> list[str]:
    return QUERY_BANK.get(topic, [])[:n]
