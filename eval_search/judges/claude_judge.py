from __future__ import annotations

import json
import logging
import re

from anthropic import AsyncAnthropic

from eval_search.judges.base import LLMJudge
from eval_search.models import JudgeScore, SearchResult

logger = logging.getLogger(__name__)


def _parse_json(text: str) -> dict:
    """Parse JSON from model output, tolerating preamble or markdown fences."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        return json.loads(m.group(1))
    m = re.search(r"\{.*?\}", text, re.DOTALL)
    if m:
        return json.loads(m.group(0))
    raise ValueError(f"No JSON in response: {text!r}")


class ClaudeJudge(LLMJudge):
    judge_id = "claude_haiku"
    model_name = "claude-haiku-4-5-20251001"

    def __init__(self, api_key: str, relevance_prompt: str | None = None, newsworthiness_prompt: str | None = None) -> None:
        super().__init__()
        self._client = AsyncAnthropic(api_key=api_key)
        if relevance_prompt is not None:
            self.relevance_prompt = relevance_prompt
        if newsworthiness_prompt is not None:
            self.newsworthiness_prompt = newsworthiness_prompt

    # claude-haiku-4-5 pricing (per token)
    _INPUT_COST_PER_TOKEN  = 0.80 / 1_000_000
    _OUTPUT_COST_PER_TOKEN = 4.00 / 1_000_000

    async def judge_result(self, result: SearchResult) -> JudgeScore:
        kwargs = dict(
            title=result.title,
            content=result.summary or result.snippet or "(no content)",
            query=result.query,
            topic_category=result.topic_category.value,
            published_date=result.raw_date_str or "unknown",
        )

        rel_score,  rel_reason,  rel_raw,  cost_rel  = await self._call(self.relevance_prompt.format(**kwargs),      "relevance")
        news_score, news_reason, news_raw, cost_news = await self._call(self.newsworthiness_prompt.format(**kwargs), "newsworthiness")

        return JudgeScore(
            judge_id=self.judge_id,
            relevance=rel_score,
            newsworthiness=news_score,
            reasoning=f"Relevance: {rel_reason} | Newsworthiness: {news_reason}",
            raw_response=json.dumps({"relevance": rel_raw, "newsworthiness": news_raw}),
            cost_usd=cost_rel + cost_news,
        )

    async def _call(self, prompt: str, key: str) -> tuple[int | None, str, str, float]:
        raw = ""
        last_err = ""
        for attempt in range(2):
            try:
                response = await self._client.messages.create(
                    model=self.model_name,
                    max_tokens=150,
                    temperature=0.0,
                    messages=[{"role": "user", "content": prompt}],
                )
                raw = response.content[0].text
                data = _parse_json(raw)
                cost = (
                    response.usage.input_tokens  * self._INPUT_COST_PER_TOKEN
                    + response.usage.output_tokens * self._OUTPUT_COST_PER_TOKEN
                )
                return data.get(key), data.get("reasoning", ""), raw, cost
            except Exception as e:
                last_err = f"{type(e).__name__}: {e}"
                if attempt == 0:
                    continue
                logger.warning("Claude judge failed for key=%s: %s — raw=%r", key, e, raw)
        return None, last_err, raw or last_err, 0.0
