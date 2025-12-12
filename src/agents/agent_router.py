"""Agent router - Routes messages to appropriate agents."""

import logging
from typing import List, Optional
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from linebot.v3.messaging import MessagingApi

from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class AgentRouter:
    """Routes incoming messages to the appropriate agent."""

    def __init__(self):
        """Initialize agent router."""
        self.agents: List[BaseAgent] = []
        logger.info("✅ Agent router initialized")

    def register_agent(self, agent: BaseAgent):
        """
        Register a new agent.

        Args:
            agent: Agent instance to register
        """
        self.agents.append(agent)
        self.agents.sort(key=lambda a: a.get_priority())  # Sort by priority
        logger.info(
            f"✅ Registered agent: {agent.name} (priority: {agent.get_priority()})"
        )

    async def route_message(
        self, event: MessageEvent, line_bot_api: MessagingApi
    ) -> bool:
        """
        Route message to first matching agent.

        Args:
            event: LINE message event
            line_bot_api: LINE Messaging API client

        Returns:
            True if message was handled by any agent
        """
        if not isinstance(event.message, TextMessageContent):
            logger.debug("Skipping non-text message")
            return False

        text = event.message.text.strip()
        logger.info(f"🔍 Routing message: '{text[:50]}...'")

        # Try each agent in priority order
        for agent in self.agents:
            if not agent.enabled:
                continue

            try:
                if await agent.should_handle(event, text):
                    logger.info(f"✅ Agent {agent.name} will handle this message")
                    success = await agent.handle(event, text, line_bot_api)

                    if success:
                        logger.info(f"✅ Message handled successfully by {agent.name}")
                        return True
                    else:
                        logger.warning(
                            f"⚠️  Agent {agent.name} failed to handle message"
                        )

            except Exception as e:
                logger.error(f"❌ Agent {agent.name} error: {e}", exc_info=True)
                continue

        logger.warning("⚠️  No agent handled this message")
        return False

    def list_agents(self) -> List[dict]:
        """
        Get list of registered agents.

        Returns:
            List of agent info dicts
        """
        return [
            {
                "name": agent.name,
                "description": agent.description,
                "priority": agent.get_priority(),
                "enabled": agent.enabled,
            }
            for agent in self.agents
        ]
