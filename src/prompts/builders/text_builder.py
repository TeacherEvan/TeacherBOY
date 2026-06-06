"""Text Prompt Builder - Placeholder for future text-based prompt construction.

This module will provide builders for text-based tasks like:
- Date extraction from messages
- Event summarization
- Conversation analysis
- Text classification

Currently: Placeholder for future implementation.
"""

import logging

logger = logging.getLogger(__name__)


class TextPromptBuilder:
    """Builder for text analysis prompts (placeholder)."""

    def __init__(self):
        """Initialize empty builder."""
        logger.warning("TextPromptBuilder is not yet implemented")
        self.template = ""

    def build(self) -> str:
        """Build the prompt."""
        return self.template or "Text prompt builder not yet implemented"
