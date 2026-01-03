"""Agent router - Routes messages to appropriate agents."""

import logging
from typing import List, Optional
from linebot.v3.webhooks import MessageEvent, TextMessageContent, ImageMessageContent
from linebot.v3.messaging import MessagingApi

from .base_agent import BaseAgent
from src.utils.tracing import get_tracer

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)


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

        Supports both text and image messages. Text is extracted for text messages,
        empty string passed for non-text messages (agents check message type directly).

        Args:
            event: LINE message event
            line_bot_api: LINE Messaging API client

        Returns:
            True if message was handled by any agent
        """
        with tracer.start_as_current_span("agent_router.route_message") as span:
            # Extract text for text messages, empty string for images/other
            if isinstance(event.message, TextMessageContent):
                text = event.message.text.strip()
                message_type = "text"
                span.set_attribute("line.message.type", "text")
                span.set_attribute("message.length", len(text))
            elif isinstance(event.message, ImageMessageContent):
                text = ""  # No text for image messages
                message_type = "image"
                span.set_attribute("line.message.type", "image")
            else:
                logger.debug(f"Skipping unsupported message type: {type(event.message)}")
                span.set_attribute("line.message.type", "unsupported")
                return False

            source = getattr(event, "source", None)
            source_type = getattr(source, "type", None) if source else None
            user_id = getattr(source, "user_id", None) if source else None
            group_id = getattr(source, "group_id", None) if source else None
            room_id = getattr(source, "room_id", None) if source else None

            if message_type == "text":
                logger.info(
                    f"🔍 Routing message ({source_type}) user_id={user_id} group_id={group_id} room_id={room_id}: '{text[:50]}...'"
                )
            else:
                logger.info(
                    f"📷 Routing {message_type} message ({source_type}) user_id={user_id} group_id={group_id} room_id={room_id}"
                )

            # Try each agent in priority order
            for agent in self.agents:
                if not agent.enabled:
                    continue

                try:
                    if await agent.should_handle(event, text):
                        logger.info(f"✅ Agent {agent.name} will handle this message")
                        span.set_attribute("agent.selected", agent.name)
                        success = await agent.handle(event, text, line_bot_api)
                        span.set_attribute("agent.success", bool(success))

                        if success:
                            logger.info(
                                f"✅ Message handled successfully by {agent.name}"
                            )
                            return True
                        else:
                            logger.warning(
                                f"⚠️  Agent {agent.name} failed to handle message"
                            )

                except Exception as e:
                    logger.error(f"❌ Agent {agent.name} error: {e}", exc_info=True)
                    span.set_attribute("agent.error", True)
                    continue

            logger.warning("⚠️  No agent handled this message")
            span.set_attribute("agent.handled", False)
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
