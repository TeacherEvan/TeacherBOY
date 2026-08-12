"""
Handler Registry - Manages dynamic loading and caching of calendar handlers.

This module implements lazy loading with importlib to minimize memory footprint
and startup time. Handlers are loaded on-demand when their triggers match.

Design Pattern: Registry Pattern + Lazy Loading + Circuit Breaker
"""

import importlib
import logging
from datetime import datetime, timedelta

from linebot.v3.messaging import MessagingApi
from linebot.v3.webhooks import MessageEvent

from .base_handler import CalendarHandler

logger = logging.getLogger(__name__)


class HandlerRegistry:
    """
    Registry for dynamically loading and caching calendar handlers.

    Features:
    - Lazy loading: Handlers loaded only when needed
    - Caching: Loaded handlers reused to avoid re-import
    - Circuit breaker: Failed handlers temporarily disabled
    - Error handling: Graceful degradation on load failures
    """

    # Handler module paths (relative to calendar package)
    HANDLER_MODULES = {
        "view": "handlers.view_handler",
        "add": "handlers.add_handler",
        "remove": "handlers.remove_handler",
        "scrape": "handlers.scrape_handler",
        "image": "handlers.image_handler",
        "inline": "handlers.inline_handler",
    }

    # Handler class names (must match class in module)
    HANDLER_CLASSES = {
        "view": "ViewHandler",
        "add": "AddHandler",
        "remove": "RemoveHandler",
        "scrape": "ScrapeHandler",
        "image": "ImageHandler",
        "inline": "InlineHandler",
    }

    def __init__(self):
        """Initialize the handler registry."""
        self._handlers: dict[str, CalendarHandler] = {}
        self._failed_handlers: dict[str, datetime] = {}
        self._failure_threshold = timedelta(minutes=5)  # Retry after 5 mins
        self._load_attempts: dict[str, int] = {}
        self._max_attempts = 3

    def get_handler(self, handler_key: str) -> CalendarHandler | None:
        """
        Get a handler by key, loading it if necessary.

        Args:
            handler_key: Handler identifier (e.g., "view", "add")

        Returns:
            Handler instance or None if loading failed
        """
        # Check if already loaded
        if handler_key in self._handlers:
            logger.debug(f"Using cached handler: {handler_key}")
            return self._handlers[handler_key]

        # Check circuit breaker
        if not self._can_attempt_load(handler_key):
            logger.warning(f"Handler {handler_key} is circuit-broken")
            return None

        # Attempt to load handler
        return self._load_handler(handler_key)

    def get_all_loaded_handlers(self) -> list[CalendarHandler]:
        """Get list of all currently loaded handlers."""
        return list(self._handlers.values())

    def preload_handlers(self, handler_keys: list[str]) -> None:
        """
        Preload specific handlers (optional optimization).

        Args:
            handler_keys: List of handler keys to preload
        """
        for key in handler_keys:
            if key not in self._handlers:
                self.get_handler(key)

    def invalidate_handler(self, handler_key: str) -> None:
        """
        Remove a handler from cache, forcing reload on next access.

        Args:
            handler_key: Handler to invalidate
        """
        if handler_key in self._handlers:
            logger.info(f"Invalidating handler: {handler_key}")
            del self._handlers[handler_key]

    def _can_attempt_load(self, handler_key: str) -> bool:
        """
        Check if we can attempt to load a handler (circuit breaker).

        Args:
            handler_key: Handler to check

        Returns:
            True if loading can be attempted
        """
        # Check if handler has failed recently
        if handler_key in self._failed_handlers:
            failure_time = self._failed_handlers[handler_key]
            if datetime.now() - failure_time < self._failure_threshold:
                return False
            # Threshold passed, remove from failed list
            del self._failed_handlers[handler_key]

        # Check attempt count
        attempts = self._load_attempts.get(handler_key, 0)
        return attempts < self._max_attempts

    def _load_handler(self, handler_key: str) -> CalendarHandler | None:
        """
        Dynamically load a handler using importlib.

        Args:
            handler_key: Handler to load

        Returns:
            Handler instance or None on failure
        """
        if handler_key not in self.HANDLER_MODULES:
            logger.error(f"Unknown handler key: {handler_key}")
            return None

        module_path = f"src.agents.calendar.{self.HANDLER_MODULES[handler_key]}"
        class_name = self.HANDLER_CLASSES[handler_key]

        try:
            logger.info(f"Loading handler: {handler_key} from {module_path}")

            # Track attempt
            self._load_attempts[handler_key] = self._load_attempts.get(handler_key, 0) + 1

            # Dynamic import
            module = importlib.import_module(module_path)
            handler_class = getattr(module, class_name)

            # Verify it's a CalendarHandler
            if not issubclass(handler_class, CalendarHandler):
                raise TypeError(f"{class_name} is not a CalendarHandler")

            # Instantiate and cache
            handler_instance = handler_class()  # type: ignore
            self._handlers[handler_key] = handler_instance

            logger.info(f"Successfully loaded handler: {handler_key}")
            return handler_instance

        except ImportError as e:
            logger.error(f"Failed to import handler {handler_key}: {e}")
            self._mark_failed(handler_key)
            return None

        except AttributeError as e:
            logger.error(f"Handler class {class_name} not found in {module_path}: {e}")
            self._mark_failed(handler_key)
            return None

        except Exception as e:
            logger.error(f"Unexpected error loading handler {handler_key}: {e}", exc_info=True)
            self._mark_failed(handler_key)
            return None

    def _mark_failed(self, handler_key: str) -> None:
        """
        Mark a handler as failed (circuit breaker).

        Args:
            handler_key: Handler that failed to load
        """
        self._failed_handlers[handler_key] = datetime.now()
        logger.warning(f"Handler {handler_key} marked as failed. Will retry after {self._failure_threshold.total_seconds()}s")

    async def find_matching_handler(
        self, event: MessageEvent, text: str, line_bot_api: MessagingApi | None
    ) -> CalendarHandler | None:
        """
        Find a handler that can process the given message.

        Iterates through handler keys, lazy-loading and checking each.

        Args:
            event: LINE message event
            text: Message text
            line_bot_api: LINE API (optional for matching)

        Returns:
            First matching handler or None
        """
        # Priority order for handler checking
        priority_order = ["inline", "view", "add", "remove", "scrape", "image"]

        for handler_key in priority_order:
            handler = self.get_handler(handler_key)
            if handler is None:
                continue

            try:
                if await handler.can_handle(event, text):
                    logger.info(f"Handler matched: {handler_key}")
                    return handler
            except Exception as e:
                logger.error(f"Error checking handler {handler_key}: {e}", exc_info=True)
                continue

        logger.debug("No matching handler found")
        return None

    def get_stats(self) -> dict:
        """Get registry statistics for monitoring."""
        return {
            "loaded_handlers": len(self._handlers),
            "failed_handlers": len(self._failed_handlers),
            "handler_list": list(self._handlers.keys()),
            "failed_list": list(self._failed_handlers.keys()),
            "load_attempts": dict(self._load_attempts),
        }


# Global registry instance
_registry_instance: HandlerRegistry | None = None


def get_handler_registry() -> HandlerRegistry:
    """
    Get the global handler registry instance (Singleton pattern).

    Returns:
        Shared HandlerRegistry instance
    """
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = HandlerRegistry()
    return _registry_instance
