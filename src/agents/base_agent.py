"""Base agent class for the multi-agent system."""

import logging
from abc import ABC, abstractmethod
from typing import Optional
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from linebot.v3.messaging import MessagingApi

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Base class for all agents in the assistant system."""

    def __init__(self, name: str, description: str):
        """
        Initialize base agent.

        Args:
            name: Agent name (e.g., "TranslationAgent")
            description: Brief description of agent's purpose
        """
        self.name = name
        self.description = description
        self.enabled = True
        logger.info(f"✅ Initialized {self.name}: {self.description}")

    @abstractmethod
    async def should_handle(self, event: MessageEvent, text: str) -> bool:
        """
        Determine if this agent should handle the message.

        Args:
            event: LINE message event
            text: Message text content

        Returns:
            True if this agent should process the message
        """
        pass

    @abstractmethod
    async def handle(
        self, event: MessageEvent, text: str, line_bot_api: MessagingApi
    ) -> bool:
        """
        Process the message.

        Args:
            event: LINE message event
            text: Message text content
            line_bot_api: LINE Messaging API client

        Returns:
            True if message was handled successfully
        """
        pass

    def get_priority(self) -> int:
        """
        Get agent priority (lower number = higher priority).

        Returns:
            Priority level (0-100)
        """
        return 50  # Default priority

    def enable(self):
        """Enable this agent."""
        self.enabled = True
        logger.info(f"✅ Enabled {self.name}")

    def disable(self):
        """Disable this agent."""
        self.enabled = False
        logger.warning(f"❌ Disabled {self.name}")

    def is_enabled(self) -> bool:
        """Check if this agent is enabled."""
        return self.enabled
