"""Centralized friend status checking with caching.

This service consolidates duplicate friend-checking logic from multiple agents
(NewsAgent, CalendarAgent, ImageAnalyzerAgent) into a single source of truth.

Performance: 5-minute caching reduces redundant LINE API calls.
Maintainability: Single update point for friend verification logic.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Tuple, Optional

from linebot.v3.messaging import MessagingApi
from linebot.v3.messaging.exceptions import ApiException

logger = logging.getLogger(__name__)


class FriendCheckService:
    """
    Centralized service for checking LINE friend status.
    
    Implements 5-minute caching to avoid redundant API calls.
    Thread-safe for concurrent agent access.
    """
    
    def __init__(self, cache_ttl_seconds: int = 300):
        """
        Initialize friend check service.
        
        Args:
            cache_ttl_seconds: Cache time-to-live in seconds (default: 5 minutes)
        """
        self._cache: Dict[str, Tuple[bool, datetime]] = {}
        self._cache_ttl = cache_ttl_seconds
        logger.info(f"🤝 FriendCheckService initialized (cache TTL: {cache_ttl_seconds}s)")
    
    async def is_friend(
        self, 
        user_id: str, 
        line_bot_api: MessagingApi
    ) -> bool:
        """
        Check if user is a LINE friend (cached).
        
        Uses LINE API get_profile() which returns error for non-friends.
        Results are cached for 5 minutes to reduce API calls.
        
        Args:
            user_id: LINE user ID
            line_bot_api: LINE Messaging API client
            
        Returns:
            True if user is a friend, False otherwise
        """
        if not user_id:
            logger.warning("🤝 No user_id provided for friend check")
            return False
        
        # Check cache first
        if user_id in self._cache:
            is_friend, cached_at = self._cache[user_id]
            age = (datetime.now(timezone.utc) - cached_at).total_seconds()
            if age < self._cache_ttl:
                logger.debug(f"🤝 Cache hit for user {user_id}: is_friend={is_friend}")
                return is_friend
        
        # Cache miss - call LINE API
        logger.debug(f"🤝 Cache miss for user {user_id}, calling LINE API...")
        
        try:
            # get_profile() succeeds only for friends
            await asyncio.to_thread(line_bot_api.get_profile, user_id)
            self._cache[user_id] = (True, datetime.now(timezone.utc))
            logger.info(f"✅ User {user_id} is a friend (verified via LINE API)")
            return True
            
        except ApiException as e:
            # Non-friends get 404 or 403
            status = getattr(e, 'status_code', 'unknown')
            self._cache[user_id] = (False, datetime.now(timezone.utc))
            logger.info(f"❌ User {user_id} is NOT a friend (ApiException: {status})")
            return False
            
        except Exception as e:
            # Other errors (network, etc.) - don't cache, return False
            logger.warning(f"⚠️ Friend check failed for {user_id}: {e}")
            return False
    
    def clear_cache(self, user_id: Optional[str] = None) -> int:
        """
        Clear friend status cache for specific user or all users.
        
        Args:
            user_id: Specific user ID to clear, or None to clear all
            
        Returns:
            Number of cache entries cleared
        """
        if user_id:
            removed = 1 if self._cache.pop(user_id, None) else 0
            logger.info(f"🤝 Cleared cache for user {user_id}")
            return removed
        else:
            count = len(self._cache)
            self._cache.clear()
            logger.info(f"🤝 Cleared entire friend cache ({count} entries)")
            return count
    
    def get_cache_stats(self) -> Dict[str, int]:
        """
        Get cache statistics.
        
        Returns:
            Dict with cache size and TTL info
        """
        return {
            "cached_users": len(self._cache),
            "cache_ttl_seconds": self._cache_ttl,
        }


# Singleton instance
friend_check_service = FriendCheckService()
