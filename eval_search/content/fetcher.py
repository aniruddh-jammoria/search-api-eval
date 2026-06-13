from __future__ import annotations

import logging

import httpx
import trafilatura

logger = logging.getLogger(__name__)

# Full browser headers — many news sites 403 anything that looks like a bot.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
}
_MAX_CHARS = 4000


async def fetch_page_text(url: str, client: httpx.AsyncClient) -> str | None:
    """Fetch URL and extract main article text. Returns None on any failure."""
    try:
        r = await client.get(url, headers=_HEADERS, follow_redirects=True, timeout=12.0)
        r.raise_for_status()
        text = trafilatura.extract(
            r.text,
            include_comments=False,
            include_tables=False,
            no_fallback=False,
        )
        if not text:
            logger.warning("trafilatura extracted no text from %s", url)
            return None
        return text[:_MAX_CHARS]
    except httpx.HTTPStatusError as e:
        logger.warning("HTTP %s fetching %s", e.response.status_code, url)
        return None
    except Exception as e:
        logger.warning("fetch_page_text failed for %s: %s", url, e)
        return None
