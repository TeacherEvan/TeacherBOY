"""Special News service.

Fetches RSS feeds asynchronously with retry logic, caching, and comprehensive error handling.
Optimized for production-grade performance and reliability.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import feedparser
import httpx

logger = logging.getLogger(__name__)


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
        self._cache: Dict[str, tuple[List[Dict[str, str]], datetime]] = {}

    async def fetch_rss_items(
        self, 
        url: str, 
        limit: int = 5,
        max_retries: int = 2
    ) -> List[Dict[str, str]]:
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

        # Fetch with retry logic
        for attempt in range(max_retries + 1):
            try:
                resp = await self._client.get(
                    url, 
                    timeout=10.0,
                    follow_redirects=True
                )
                resp.raise_for_status()

                parsed = feedparser.parse(resp.text)
                items: List[Dict[str, str]] = []
                
                for entry in getattr(parsed, "entries", [])[:limit * 2]:  # Fetch extra in case some are invalid
                    title = getattr(entry, "title", "") or ""
                    link = getattr(entry, "link", "") or ""
                    
                    # Skip entries without titles
                    if not title or not title.strip():
                        continue
                        
                    items.append({
                        "title": title.strip(),
                        "url": link.strip()
                    })
                    
                    # Stop once we have enough valid items
                    if len(items) >= limit:
                        break

                # Cache successful results
                if items:
                    self._add_to_cache(url, items)
                    logger.info(f"✅ Fetched {len(items)} items from {self._get_feed_name(url)}")
                else:
                    logger.warning(f"⚠️ No valid entries found in {url}")
                
                return items[:limit]
                
            except httpx.TimeoutException:
                logger.warning(f"⏱️ Timeout fetching {url} (attempt {attempt + 1}/{max_retries + 1})")
                if attempt < max_retries:
                    # Exponential backoff: 0.5s, 1s, 2s...
                    await asyncio.sleep(0.5 * (2 ** attempt))
                    
            except httpx.HTTPStatusError as e:
                logger.error(f"❌ HTTP {e.response.status_code} for {url}")
                break  # Don't retry on client/server errors
                
            except Exception as e:
                logger.error(f"❌ RSS fetch failed for {url}: {type(e).__name__}: {e}")
                if attempt < max_retries:
                    await asyncio.sleep(0.5 * (2 ** attempt))

        # All retries exhausted
        logger.error(f"❌ Failed to fetch {url} after {max_retries + 1} attempts")
        return []

    def _get_from_cache(self, url: str) -> Optional[List[Dict[str, str]]]:
        """Retrieve cached items if not expired."""
        if url not in self._cache:
            return None
            
        items, cached_at = self._cache[url]
        age_seconds = (datetime.now(timezone.utc) - cached_at).total_seconds()
        
        if age_seconds < self._cache_ttl_seconds:
            return items
            
        # Expired - remove from cache
        del self._cache[url]
        return None

    def _add_to_cache(self, url: str, items: List[Dict[str, str]]) -> None:
        """Add items to cache with current timestamp."""
        self._cache[url] = (items, datetime.now(timezone.utc))

    def _get_feed_name(self, url: str) -> str:
        """Extract human-readable feed name from URL."""
        if "tatnews" in url:
            return "Thailand Tourism"
        elif "sports" in url:
            return "Sports"
        elif "world" in url or "international" in url:
            return "International"
        return "RSS Feed"

    @staticmethod
    def pad_items(items: List[Dict[str, str]], limit: int = 5) -> List[Dict[str, str]]:
        """Ensure exactly `limit` items by padding with placeholders."""
        padded = list(items[:limit])
        while len(padded) < limit:
            padded.append({"title": "(unavailable)", "url": ""})
        return padded
