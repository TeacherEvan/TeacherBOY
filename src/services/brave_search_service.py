"""
Brave Search Service - Web search capabilities using Brave Search API.
"""

import logging
import httpx
from typing import List, Dict, Optional, Any
from src.config import settings

logger = logging.getLogger(__name__)


class BraveSearchService:
    """Service for performing web searches using Brave Search API."""

    def __init__(self, http_client: Optional[httpx.AsyncClient] = None):
        """
        Initialize Brave Search service.

        Args:
            http_client: Shared async HTTP client
        """
        self.client = http_client
        self.api_url = "https://api.search.brave.com/res/v1/web/search"
        self.api_key = settings.brave_search_api_key

    def set_client(self, client: httpx.AsyncClient):
        """Set the shared HTTP client."""
        self.client = client

    def is_configured(self) -> bool:
        """Check if Brave Search is configured."""
        return settings.is_brave_search_configured()

    async def search(self, query: str, count: int = 5) -> List[Dict[str, str]]:
        """
        Perform a web search.

        Args:
            query: Search query
            count: Number of results to return (max 20)

        Returns:
            List of dicts with 'title', 'url', 'description'
        """
        if not self.is_configured():
            logger.warning("⚠️ Brave Search API key not configured")
            return []

        if not self.client:
            logger.warning("⚠️ HTTP client not available for search")
            return []

        try:
            headers = {
                "X-Subscription-Token": self.api_key,
                "Accept": "application/json",
            }
            params = {
                "q": query,
                "count": min(count, 20),
                "safesearch": "moderate",
            }

            response = await self.client.get(
                self.api_url, headers=headers, params=params, timeout=10.0
            )
            response.raise_for_status()
            data = response.json()

            results = []
            web_results = data.get("web", {}).get("results", [])

            for item in web_results:
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "description": item.get("description", "")
                })

            logger.info(f"🔍 Brave Search found {len(results)} results for '{query}'")
            return results

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                logger.warning("⚠️ Brave Search rate limit exceeded")
            else:
                logger.error(f"❌ Brave Search HTTP error: {e}")
            return []
        except Exception as e:
            logger.error(f"❌ Brave Search error: {e}", exc_info=True)
            return []


# Singleton instance
brave_search_service = BraveSearchService()
