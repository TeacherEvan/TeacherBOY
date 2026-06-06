"""Special News service.

Fetches RSS feeds asynchronously with retry logic, caching, and comprehensive error handling.
Optimized for production-grade performance and reliability.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

import feedparser
import httpx

logger = logging.getLogger(__name__)

# Constants
TITLE_TRUNCATE_LENGTH = 50  # Max characters to show in log messages


class SpecialNewsService:
    """
    Production-grade RSS feed fetcher for special news feature.

    Features:
    - Automatic retry with exponential backoff
    - In-memory caching with TTL
    - Concurrent fetch optimization
    - Comprehensive error handling
    """

    def __init__(self, http_client: httpx.AsyncClient, cache_ttl_seconds: int = 300):
        """
        Initialize special news service.

        Args:
            http_client: Shared async HTTP client for connection pooling
            cache_ttl_seconds: Cache time-to-live in seconds (default: 5 minutes)
        """
        self._client = http_client
        self._cache_ttl_seconds = cache_ttl_seconds
        self._cache: dict[str, tuple[list[dict[str, str]], datetime]] = {}

    async def fetch_rss_items(self, url: str, limit: int = 5, max_retries: int = 3) -> list[dict[str, str]]:
        """
        Fetch RSS/Atom feed with retry logic and caching.

        Args:
            url: RSS feed URL
            limit: Maximum number of items to return
            max_retries: Number of retry attempts on failure

        Returns:
            List of {title, url} dictionaries, empty list on failure
        """
        # Check cache first
        cached_items = self._get_from_cache(url)
        if cached_items is not None:
            logger.debug(f"📦 Cache hit for {url}")
            return cached_items[:limit]

        feed_name = self._get_feed_name(url)
        logger.info(f"🔍 Fetching {feed_name} from {url}")

        # Fetch with retry logic
        for attempt in range(max_retries + 1):
            try:
                resp = await self._client.get(
                    url,
                    timeout=15.0,  # Increased from 10s to 15s
                    follow_redirects=True,
                )
                resp.raise_for_status()

                # Log response details for debugging
                logger.debug(
                    f"📥 Response: {len(resp.text)} bytes, Content-Type: {resp.headers.get('content-type', 'unknown')}"
                )

                parsed = feedparser.parse(resp.text)

                # Check if feedparser encountered errors
                if hasattr(parsed, "bozo") and parsed.bozo and hasattr(parsed, "bozo_exception"):
                    logger.warning(f"⚠️ Feedparser warning for {url}: {parsed.bozo_exception}")

                entries = getattr(parsed, "entries", [])
                logger.info(f"📋 Parsed {len(entries)} entries from {feed_name}")

                items: list[dict[str, str]] = []

                for entry in entries[: limit * 2]:  # Fetch extra in case some are invalid
                    title = getattr(entry, "title", "") or ""
                    link = getattr(entry, "link", "") or ""

                    # Skip entries without titles
                    if not title or not title.strip():
                        logger.debug("⏭️ Skipping entry with empty title")
                        continue

                    # Validate URL exists
                    if not link or not link.strip():
                        logger.warning(f"⚠️ Entry '{title[:TITLE_TRUNCATE_LENGTH]}...' has no URL")

                    items.append({"title": title.strip(), "url": link.strip()})

                    # Stop once we have enough valid items
                    if len(items) >= limit:
                        break

                # Cache successful results
                if items:
                    self._add_to_cache(url, items)
                    logger.info(f"✅ Fetched {len(items)} items from {feed_name}")
                else:
                    logger.warning(f"⚠️ No valid entries found in {feed_name}")

                return items[:limit]

            except httpx.TimeoutException:
                logger.warning(f"⏱️ Timeout fetching {feed_name} (attempt {attempt + 1}/{max_retries + 1})")
                if attempt < max_retries:
                    # Exponential backoff: 1s, 2s, 4s...
                    backoff = 1.0 * (2**attempt)
                    logger.debug(f"⏳ Retrying in {backoff}s...")
                    await asyncio.sleep(backoff)

            except httpx.HTTPStatusError as e:
                logger.error(f"❌ HTTP {e.response.status_code} for {feed_name}: {url}")
                break  # Don't retry on client/server errors

            except Exception as e:
                logger.error(f"❌ RSS fetch failed for {feed_name}: {type(e).__name__}: {e}", exc_info=True)
                if attempt < max_retries:
                    backoff = 1.0 * (2**attempt)
                    await asyncio.sleep(backoff)

        # All retries exhausted
        logger.error(f"❌ Failed to fetch {feed_name} after {max_retries + 1} attempts")
        return []

    def _get_from_cache(self, url: str) -> list[dict[str, str]] | None:
        """Retrieve cached items if not expired."""
        if url not in self._cache:
            return None

        items, cached_at = self._cache[url]
        age_seconds = (datetime.now(UTC) - cached_at).total_seconds()

        if age_seconds < self._cache_ttl_seconds:
            return items

        # Expired - remove from cache
        del self._cache[url]
        return None

    def _add_to_cache(self, url: str, items: list[dict[str, str]]) -> None:
        """Add items to cache with current timestamp."""
        self._cache[url] = (items, datetime.now(UTC))

    def _get_feed_name(self, url: str) -> str:
        """Extract human-readable feed name from URL."""
        if "tatnews" in url or "travel" in url:
            return "Thailand Tourism"
        elif "sports" in url:
            return "Sports"
        elif "world" in url or "international" in url:
            return "International"
        return "RSS Feed"

    @staticmethod
    def pad_items(items: list[dict[str, str]], limit: int = 5) -> list[dict[str, str]]:
        """Ensure exactly `limit` items by padding with placeholders."""
        padded = list(items[:limit])
        while len(padded) < limit:
            padded.append({"title": "(unavailable)", "url": ""})
        return padded
