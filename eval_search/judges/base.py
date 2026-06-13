from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod

from eval_search.judges.prompts import NEWSWORTHINESS_PROMPT, RELEVANCE_PROMPT
from eval_search.models import JudgeScore, SearchResult


class LLMJudge(ABC):
    judge_id: str
    model_name: str

    def __init__(self) -> None:
        self.relevance_prompt: str = RELEVANCE_PROMPT
        self.newsworthiness_prompt: str = NEWSWORTHINESS_PROMPT

    @abstractmethod
    async def judge_result(self, result: SearchResult) -> JudgeScore:
        ...

    async def judge_batch(
        self,
        results: list[SearchResult],
        concurrency: int = 8,
    ) -> list[JudgeScore]:
        sem = asyncio.Semaphore(concurrency)

        async def bounded(r: SearchResult) -> JudgeScore:
            async with sem:
                return await self.judge_result(r)

        return list(await asyncio.gather(*[bounded(r) for r in results]))
