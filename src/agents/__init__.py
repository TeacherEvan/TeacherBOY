"""Agent system for TeacherBOY - Multi-agent architecture."""

from .base_agent import BaseAgent
from .translation_agent import TranslationAgent
from .agent_router import AgentRouter

__all__ = ["BaseAgent", "TranslationAgent", "AgentRouter"]
