"""
Conversation Summarization Service - Intelligent conversation compression.

This service provides automatic conversation summarization to:
- Reduce token usage in long conversations
- Maintain context continuity
- Preserve critical information
- Enable long-running conversations

Uses configurable summarization strategies with LLM-powered compression.
"""

import logging
from typing import List, Dict, Optional, Any
from datetime import datetime
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ConversationSummary:
    """Represents a summarized conversation segment."""
    
    summary_text: str
    original_message_count: int
    compressed_token_count: int
    original_token_count: int
    compression_ratio: float
    created_at: datetime
    covered_topics: List[str]
    metadata: Dict[str, Any]


class ConversationSummarizationService:
    """
    Service for summarizing long conversations to reduce token usage.
    
    Key features:
    - Automatic summarization when conversation exceeds threshold
    - Multi-level summarization for very long conversations
    - Topic extraction and key point preservation
    - Configurable compression strategies
    """
    
    # Summarization prompt template
    SUMMARIZATION_PROMPT = """You are an expert at summarizing conversations concisely while preserving critical information.

Analyze the following conversation and create a comprehensive summary that:
1. Captures all key points and decisions
2. Preserves important context and user preferences
3. Maintains temporal awareness (when things happened)
4. Identifies main topics discussed
5. Notes any pending actions or unresolved questions

Conversation to summarize:
{conversation}

Provide your response in this format:

## Summary
[Comprehensive summary of the conversation]

## Key Topics
- Topic 1
- Topic 2
- Topic 3

## Important Context
[Any critical context that must be preserved]

## Pending Actions
[Any unresolved items or pending tasks]

Keep the summary concise but complete. Focus on information that would be valuable for continuing the conversation."""
    
    def __init__(self, llm_service: Optional[Any] = None):
        """
        Initialize conversation summarization service.
        
        Args:
            llm_service: LLM service for summarization (GitHub Models or OpenRouter)
        """
        self._llm_service = llm_service
        self._summary_count = 0
        logger.info("📝 ConversationSummarizationService initialized")
    
    def set_llm_service(self, service: Any) -> None:
        """Set the LLM service for summarization."""
        self._llm_service = service
        logger.info("📝 LLM service configured for summarization")
    
    async def should_summarize(
        self,
        messages: List[Dict[str, str]],
        token_threshold: int = 50000,
        message_threshold: int = 50,
    ) -> bool:
        """
        Determine if conversation should be summarized.
        
        Args:
            messages: List of conversation messages
            token_threshold: Summarize if conversation exceeds this token count
            message_threshold: Summarize if message count exceeds this
            
        Returns:
            True if conversation should be summarized
        """
        if len(messages) < 10:
            return False  # Too short to summarize
        
        # Check message count threshold
        if len(messages) >= message_threshold:
            logger.info(
                f"📝 Conversation exceeds message threshold: "
                f"{len(messages)} >= {message_threshold}"
            )
            return True
        
        # Estimate total tokens
        total_chars = sum(len(msg.get("content", "")) for msg in messages)
        estimated_tokens = total_chars // 4  # Rough approximation
        
        if estimated_tokens >= token_threshold:
            logger.info(
                f"📝 Conversation exceeds token threshold: "
                f"~{estimated_tokens} >= {token_threshold}"
            )
            return True
        
        return False
    
    async def summarize_conversation(
        self,
        messages: List[Dict[str, str]],
        preserve_recent: int = 5,
        model: str = "openai/gpt-4o-mini",
    ) -> Optional[ConversationSummary]:
        """
        Summarize a conversation using LLM.
        
        Strategy:
        1. Keep most recent N messages as-is (for continuity)
        2. Summarize older messages into compressed format
        3. Extract key topics and context
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            preserve_recent: Number of recent messages to keep unsummarized
            model: Model to use for summarization
            
        Returns:
            ConversationSummary or None if summarization failed
        """
        if not self._llm_service:
            logger.warning("📝 No LLM service configured, cannot summarize")
            return None
        
        if len(messages) <= preserve_recent:
            logger.info("📝 Conversation too short to summarize")
            return None
        
        # Split into messages to summarize and recent messages to preserve
        messages_to_summarize = messages[:-preserve_recent] if preserve_recent > 0 else messages
        
        # Format conversation for summarization
        conversation_text = self._format_messages_for_summary(messages_to_summarize)
        
        # Build summarization prompt
        prompt = self.SUMMARIZATION_PROMPT.format(conversation=conversation_text)
        
        try:
            # Call LLM for summarization
            logger.info(
                f"📝 Summarizing {len(messages_to_summarize)} messages "
                f"(preserving {preserve_recent} recent)"
            )
            
            # Use GitHub Models Service or OpenRouter
            response = await self._llm_service.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                model=model,
                temperature=0.3,  # Lower temperature for consistent summaries
                max_tokens=2000,
            )
            
            if not response:
                logger.error("📝 Summarization failed: no response from LLM")
                return None
            
            # Parse summary and extract topics
            summary_text = response
            topics = self._extract_topics_from_summary(summary_text)
            
            # Calculate compression metrics
            original_chars = sum(len(msg.get("content", "")) for msg in messages_to_summarize)
            original_tokens = original_chars // 4
            compressed_tokens = len(summary_text) // 4
            compression_ratio = compressed_tokens / original_tokens if original_tokens > 0 else 0
            
            self._summary_count += 1
            
            logger.info(
                f"📝 Summarization complete: "
                f"{original_tokens} → {compressed_tokens} tokens "
                f"({compression_ratio*100:.1f}% compression)"
            )
            
            return ConversationSummary(
                summary_text=summary_text,
                original_message_count=len(messages_to_summarize),
                compressed_token_count=compressed_tokens,
                original_token_count=original_tokens,
                compression_ratio=compression_ratio,
                created_at=datetime.now(),
                covered_topics=topics,
                metadata={
                    "model": model,
                    "preserve_recent": preserve_recent,
                }
            )
            
        except Exception as e:
            logger.error(f"📝 Summarization error: {e}", exc_info=True)
            return None
    
    def _format_messages_for_summary(self, messages: List[Dict[str, str]]) -> str:
        """Format messages into readable conversation text."""
        formatted_lines = []
        
        for i, msg in enumerate(messages, 1):
            role = msg.get("role", "user")
            content = msg.get("content", "")
            timestamp = msg.get("timestamp", "")
            
            if timestamp:
                formatted_lines.append(f"[{i}] {role.title()} ({timestamp}): {content}")
            else:
                formatted_lines.append(f"[{i}] {role.title()}: {content}")
        
        return "\n\n".join(formatted_lines)
    
    def _extract_topics_from_summary(self, summary_text: str) -> List[str]:
        """Extract key topics from summary text."""
        topics = []
        
        # Simple extraction: look for "Key Topics" section
        if "## Key Topics" in summary_text:
            lines = summary_text.split("\n")
            in_topics = False
            for line in lines:
                if "## Key Topics" in line:
                    in_topics = True
                    continue
                elif line.startswith("##"):
                    in_topics = False
                elif in_topics and line.strip().startswith("-"):
                    topic = line.strip()[1:].strip()
                    topics.append(topic)
        
        return topics
    
    def create_compressed_history(
        self,
        summary: ConversationSummary,
        recent_messages: List[Dict[str, str]],
    ) -> List[Dict[str, str]]:
        """
        Create a compressed conversation history combining summary and recent messages.
        
        Args:
            summary: ConversationSummary object
            recent_messages: Recent unsummarized messages
            
        Returns:
            List of messages with summary replacing older messages
        """
        # Create a summary message to replace the older conversation
        summary_message = {
            "role": "assistant",
            "content": f"[Previous conversation summary]\n\n{summary.summary_text}",
            "timestamp": summary.created_at.isoformat(),
            "metadata": {
                "is_summary": True,
                "original_message_count": summary.original_message_count,
                "compression_ratio": summary.compression_ratio,
            }
        }
        
        # Combine summary with recent messages
        compressed_history = [summary_message] + recent_messages
        
        logger.info(
            f"📝 Created compressed history: "
            f"{len(compressed_history)} messages "
            f"(summary + {len(recent_messages)} recent)"
        )
        
        return compressed_history
    
    def get_summary_stats(self) -> Dict[str, int]:
        """Get service statistics."""
        return {
            "total_summaries": self._summary_count,
        }


# Singleton instance (needs LLM service injection)
conversation_summarization_service = ConversationSummarizationService()
