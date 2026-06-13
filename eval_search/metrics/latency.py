from __future__ import annotations

import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncGenerator


@dataclass
class LatencyCapture:
    ms: float = 0.0


@asynccontextmanager
async def measure_latency() -> AsyncGenerator[LatencyCapture, None]:
    cap = LatencyCapture()
    start = time.perf_counter()
    try:
        yield cap
    finally:
        cap.ms = round((time.perf_counter() - start) * 1000, 2)
