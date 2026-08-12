"""Prompts package - Modular, reusable prompt templates.

This package provides:
- Reusable knowledge frameworks (FBI, FACS, etc.)
- Dynamic prompt builders for vision and text tasks
- Centralized prompt registry for versioning and A/B testing

Design goals:
- Reduce token waste through selective framework loading
- Enable easy A/B testing of prompt variations
- Track token usage per prompt component
- Version control for prompt evolution
"""

from .builders.debrief_builder import DebriefPromptBuilder, build_debrief_prompt
from .builders.vision_builder import VisionPromptBuilder

__all__ = [
    "VisionPromptBuilder",
    "DebriefPromptBuilder",
    "build_debrief_prompt",
]
