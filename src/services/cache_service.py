"""Cache service for in-memory TTL caching."""

import logging
from typing import Any

logger = logging.getLogger(__name__)

try:
    from cachetools import TTLCache

    CACHETOOLS_AVAILABLE = True
except ImportError:
    logger.warning("cachetools not available, caching disabled")
    CACHETOOLS_AVAILABLE = False
    TTLCache = None


class CacheService:
    """Simple in-memory TTL cache service."""

    def __init__(self):
        """Initialize cache service."""
        self._caches = {}
        if CACHETOOLS_AVAILABLE:
            logger.info("✅ Cache service initialized with TTL caching")
        else:
            logger.warning("⚠️  Cache service initialized without TTL caching (cachetools not available)")

    def get_cache(self, name: str, maxsize: int = 1000, ttl: int = 3600):
        """
        Get or create a TTL cache.

        Args:
            name: Cache name/identifier
            maxsize: Maximum cache size
            ttl: Time-to-live in seconds

        Returns:
            TTLCache instance or None if cachetools not available
        """
        if not CACHETOOLS_AVAILABLE:
            return None

        if name not in self._caches:
            self._caches[name] = TTLCache(maxsize=maxsize, ttl=ttl)
            logger.debug(f"Created cache '{name}' with maxsize={maxsize}, ttl={ttl}")
        return self._caches[name]

    def get(self, cache_name: str, key: str) -> Any | None:
        """
        Get value from cache.

        Args:
            cache_name: Name of the cache
            key: Cache key

        Returns:
            Cached value or None if not found or caching disabled
        """
        if not CACHETOOLS_AVAILABLE:
            return None

        cache = self._caches.get(cache_name)
        if cache is None:
            return None
        return cache.get(key)

    def set(self, cache_name: str, key: str, value: Any, ttl: int | None = None) -> None:
        """
        Set value in cache.

        Args:
            cache_name: Name of the cache
            key: Cache key
            value: Value to cache
            ttl: Optional TTL override
        """
        if not CACHETOOLS_AVAILABLE:
            return

        cache = self._caches.get(cache_name)
        if cache is not None:
            cache[key] = value
            if ttl is not None:
                # Note: cachetools doesn't support per-item TTL easily
                # This is a simplification
                pass

    def clear(self, cache_name: str) -> None:
        """
        Clear a specific cache.

        Args:
            cache_name: Name of the cache to clear
        """
        if not CACHETOOLS_AVAILABLE:
            return

        if cache_name in self._caches:
            self._caches[cache_name].clear()
            logger.info(f"Cleared cache '{cache_name}'")

    def clear_all(self) -> None:
        """Clear all caches."""
        if not CACHETOOLS_AVAILABLE:
            return

        for name in self._caches:
            self._caches[name].clear()
        logger.info("Cleared all caches")


# Global cache service instance
cache_service = CacheService()
