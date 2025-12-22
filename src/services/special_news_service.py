"""Special News service.

Fetches RSS feeds asynchronously and returns normalized headline items.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import feedparser
import httpx

logger = logging.getLogger(__name__)


class SpecialNewsService:
    """Fetches three RSS feeds (tourism/sports/international) for /special news."""

    def __init__(self, http_client: httpx.AsyncClient):
        self._client = http_client

    async def fetch_rss_items(self, url: str, limit: int = 5) -> List[Dict[str, str]]:
        """Fetch RSS/Atom feed and return a list of {title, url} items."""
        try:
            resp = await self._client.get(url, timeout=10.0)
            resp.raise_for_status()

            parsed = feedparser.parse(resp.text)
            items: List[Dict[str, str]] = []
            for entry in getattr(parsed, "entries", [])[:limit]:
                title = getattr(entry, "title", "") or ""
                link = getattr(entry, "link", "") or ""
                if title:
                    items.append({"title": title.strip(), "url": link.strip()})

            return items
        except Exception as e:
            logger.error(f"📰 SpecialNews RSS fetch failed for {url}: {e}")
            return []

    @staticmethod
    def pad_items(items: List[Dict[str, str]], limit: int = 5) -> List[Dict[str, str]]:
        """Ensure exactly `limit` items by padding with placeholders."""
        padded = list(items[:limit])
        while len(padded) < limit:
            padded.append({"title": "(unavailable)", "url": ""})
        return padded
