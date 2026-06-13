from __future__ import annotations

import json
import logging
import re

from anthropic import AsyncAnthropic

logger = logging.getLogger(__name__)

_INPUT_COST_PER_TOKEN = 0.80 / 1_000_000
_OUTPUT_COST_PER_TOKEN = 4.00 / 1_000_000
_MODEL = "claude-haiku-4-5-20251001"
_MAX_CONTENT_CHARS = 3000


def _build_prompt(title: str, content: str) -> str:
    # Use string concatenation rather than .format() so that article text
    # containing {placeholders} (common in tech articles) doesn't raise KeyError.
    return (
        "Summarize the following article in 3 sentences for a newsletter curation system. "
        "Be specific: include names, numbers, and concrete facts. Skip marketing language.\n\n"
        "Title: " + title + "\n"
        "Content: " + content[:_MAX_CONTENT_CHARS] + "\n\n"
        'Return ONLY valid JSON: {"summary": "<3 sentences>"}'
    )


def _parse_json(raw: str) -> dict:
    s = raw.strip()
    # Strip markdown fences if the model wrapped its response
    if s.startswith("```"):
        s = re.sub(r"^```[a-z]*\n?", "", s)
        s = re.sub(r"\n?```$", "", s.strip())
    # Find the outermost JSON object
    m = re.search(r"\{[\s\S]*\}", s)
    return json.loads(m.group(0) if m else s)


async def summarize(title: str, content: str, client: AsyncAnthropic) -> tuple[str, float]:
    """Returns (summary, cost_usd). Falls back to truncated content on any failure."""
    try:
        response = await client.messages.create(
            model=_MODEL,
            max_tokens=200,
            temperature=0.0,
            messages=[{"role": "user", "content": _build_prompt(title, content)}],
        )
        raw = response.content[0].text
        data = _parse_json(raw)
        cost = (
            response.usage.input_tokens * _INPUT_COST_PER_TOKEN
            + response.usage.output_tokens * _OUTPUT_COST_PER_TOKEN
        )
        return data.get("summary") or content[:300], cost
    except Exception as e:
        logger.warning("summarize failed for %r: %s", title[:60], e)
        return content[:300], 0.0
