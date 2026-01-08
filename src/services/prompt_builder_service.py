"""
Prompt Builder Service - Intelligent prompt construction with token optimization.

This service provides intelligent prompt building capabilities with:
- Token-aware truncation
- Priority-based context inclusion
- Dynamic context fitting
- Cost estimation

Designed to maximize LLM performance while minimizing token costs.
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Token estimation constants (rough approximations)
CHARS_PER_TOKEN = 4  # Average characters per token for English/Thai mixed text
MAX_TOKENS_GPT4O = 128000  # GPT-4o context window
MAX_TOKENS_GPT4O_MINI = 128000  # GPT-4o-mini context window
MAX_TOKENS_GEMMA = 8192  # Gemma 2 9B context window


@dataclass
class ContextBlock:
    """Represents a block of context with priority and metadata."""
    
    content: str
    priority: int  # Lower number = higher priority (0 = critical)
    label: str
    estimated_tokens: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Calculate estimated tokens on initialization."""
        if self.estimated_tokens == 0:
            self.estimated_tokens = len(self.content) // CHARS_PER_TOKEN


@dataclass
class PromptBuildResult:
    """Result of prompt building operation."""
    
    final_prompt: str
    total_tokens: int
    included_blocks: List[str]
    excluded_blocks: List[str]
    token_budget_used: float  # Percentage of budget used
    estimated_cost_usd: float = 0.0


class PromptBuilderService:
    """
    Service for building intelligent, token-optimized prompts.
    
    Key features:
    - Priority-based context inclusion
    - Token budget management
    - Dynamic truncation
    - Cost estimation
    """
    
    def __init__(self):
        """Initialize prompt builder service."""
        self._build_count = 0
        logger.info("🔧 PromptBuilderService initialized")
    
    def build_prompt(
        self,
        system_prompt: str,
        user_message: str,
        context_blocks: List[ContextBlock],
        max_tokens: int = MAX_TOKENS_GPT4O_MINI,
        reserve_tokens: int = 2000,  # Reserve for response
        model: str = "gpt-4o-mini",
    ) -> PromptBuildResult:
        """
        Build an optimized prompt with priority-based context inclusion.
        
        Strategy:
        1. Always include system prompt and user message (critical)
        2. Sort context blocks by priority (0 = highest)
        3. Include blocks until token budget exhausted
        4. Truncate lowest priority blocks if needed
        
        Args:
            system_prompt: System instructions (always included)
            user_message: User's message (always included)
            context_blocks: List of context blocks with priorities
            max_tokens: Maximum context window size
            reserve_tokens: Tokens to reserve for response
            model: Model name for cost estimation
            
        Returns:
            PromptBuildResult with final prompt and metadata
        """
        # Calculate available token budget
        available_tokens = max_tokens - reserve_tokens
        
        # Estimate core tokens (system + user message)
        system_tokens = len(system_prompt) // CHARS_PER_TOKEN
        user_tokens = len(user_message) // CHARS_PER_TOKEN
        core_tokens = system_tokens + user_tokens
        
        if core_tokens > available_tokens:
            logger.warning(
                f"⚠️ Core prompt ({core_tokens} tokens) exceeds budget "
                f"({available_tokens} tokens). Truncating user message."
            )
            # Truncate user message to fit
            allowed_user_tokens = available_tokens - system_tokens - 100  # Safety margin
            max_chars = allowed_user_tokens * CHARS_PER_TOKEN
            user_message = user_message[:max_chars] + "\n\n[Message truncated]"
            user_tokens = len(user_message) // CHARS_PER_TOKEN
            core_tokens = system_tokens + user_tokens
        
        # Remaining budget for context blocks
        context_budget = available_tokens - core_tokens
        
        # Sort context blocks by priority (lower = higher priority)
        sorted_blocks = sorted(context_blocks, key=lambda b: b.priority)
        
        # Greedily include blocks until budget exhausted
        included_blocks: List[ContextBlock] = []
        excluded_blocks: List[str] = []
        tokens_used = 0
        
        for block in sorted_blocks:
            if tokens_used + block.estimated_tokens <= context_budget:
                included_blocks.append(block)
                tokens_used += block.estimated_tokens
            else:
                # Try to include truncated version of this block
                remaining_budget = context_budget - tokens_used
                if remaining_budget > 100:  # Only include if meaningful space left
                    truncated_chars = remaining_budget * CHARS_PER_TOKEN
                    truncated_content = block.content[:truncated_chars] + "\n\n[Context truncated]"
                    truncated_block = ContextBlock(
                        content=truncated_content,
                        priority=block.priority,
                        label=f"{block.label} (truncated)",
                        estimated_tokens=remaining_budget
                    )
                    included_blocks.append(truncated_block)
                    tokens_used += remaining_budget
                    excluded_blocks.append(f"{block.label} (partial)")
                else:
                    excluded_blocks.append(block.label)
        
        # Construct final prompt
        context_parts = [block.content for block in included_blocks]
        context_section = "\n\n".join(context_parts) if context_parts else ""
        
        if context_section:
            final_prompt = f"{system_prompt}\n\n{context_section}\n\n{user_message}"
        else:
            final_prompt = f"{system_prompt}\n\n{user_message}"
        
        total_tokens = core_tokens + tokens_used
        budget_used = (total_tokens / available_tokens) * 100
        
        # Estimate cost (rough approximation)
        cost_usd = self._estimate_cost(total_tokens, model)
        
        self._build_count += 1
        
        logger.info(
            f"🔧 Built prompt: {total_tokens}/{available_tokens} tokens "
            f"({budget_used:.1f}% used), included {len(included_blocks)}/{len(sorted_blocks)} blocks"
        )
        
        if excluded_blocks:
            logger.debug(f"🔧 Excluded blocks: {', '.join(excluded_blocks)}")
        
        return PromptBuildResult(
            final_prompt=final_prompt,
            total_tokens=total_tokens,
            included_blocks=[b.label for b in included_blocks],
            excluded_blocks=excluded_blocks,
            token_budget_used=budget_used,
            estimated_cost_usd=cost_usd,
        )
    
    def _estimate_cost(self, tokens: int, model: str) -> float:
        """
        Estimate cost in USD for a given token count.
        
        Pricing (as of Jan 2025):
        - GPT-4o: $2.50 per 1M input tokens
        - GPT-4o-mini: $0.15 per 1M input tokens
        - Gemma 2 9B: Free (GitHub Models)
        
        Args:
            tokens: Number of tokens
            model: Model name
            
        Returns:
            Estimated cost in USD
        """
        model_lower = model.lower()
        
        # Cost per million tokens
        if "gpt-4o-mini" in model_lower:
            cost_per_million = 0.15
        elif "gpt-4o" in model_lower:
            cost_per_million = 2.50
        elif "gemma" in model_lower or "github" in model_lower:
            return 0.0  # Free via GitHub Models
        else:
            cost_per_million = 0.15  # Conservative default
        
        return (tokens / 1_000_000) * cost_per_million
    
    def create_conversation_context(
        self,
        messages: List[Dict[str, str]],
        max_messages: int = 10,
        priority: int = 2,
    ) -> ContextBlock:
        """
        Create a context block from conversation history.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            max_messages: Maximum messages to include
            priority: Priority level (lower = higher priority)
            
        Returns:
            ContextBlock with formatted conversation
        """
        recent_messages = messages[-max_messages:] if len(messages) > max_messages else messages
        
        formatted_lines = ["## Recent Conversation"]
        for msg in recent_messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            formatted_lines.append(f"**{role.title()}**: {content}")
        
        context = "\n".join(formatted_lines)
        
        return ContextBlock(
            content=context,
            priority=priority,
            label="conversation_history",
            metadata={"message_count": len(recent_messages)}
        )
    
    def create_user_profile_context(
        self,
        user_id: str,
        preferences: Optional[Dict[str, Any]] = None,
        priority: int = 3,
    ) -> ContextBlock:
        """
        Create a context block for user profile information.
        
        Args:
            user_id: User identifier
            preferences: User preferences dict
            priority: Priority level
            
        Returns:
            ContextBlock with user profile
        """
        lines = [
            "## User Profile",
            f"User ID: {user_id}",
        ]
        
        if preferences:
            lines.append("\n### Preferences")
            for key, value in preferences.items():
                lines.append(f"- {key}: {value}")
        
        context = "\n".join(lines)
        
        return ContextBlock(
            content=context,
            priority=priority,
            label="user_profile",
            metadata={"user_id": user_id}
        )
    
    def create_system_state_context(
        self,
        current_time: Optional[datetime] = None,
        session_data: Optional[Dict[str, Any]] = None,
        priority: int = 1,
    ) -> ContextBlock:
        """
        Create a context block for system state information.
        
        Args:
            current_time: Current timestamp
            session_data: Session state data
            priority: Priority level (default: 1 = high priority)
            
        Returns:
            ContextBlock with system state
        """
        if current_time is None:
            current_time = datetime.now()
        
        lines = [
            "## System Context",
            f"Current Time: {current_time.strftime('%Y-%m-%d %H:%M:%S')}",
        ]
        
        if session_data:
            lines.append("\n### Session State")
            for key, value in session_data.items():
                lines.append(f"- {key}: {value}")
        
        context = "\n".join(lines)
        
        return ContextBlock(
            content=context,
            priority=priority,
            label="system_state",
            metadata={"timestamp": current_time.isoformat()}
        )
    
    def get_build_stats(self) -> Dict[str, int]:
        """Get service statistics."""
        return {
            "total_builds": self._build_count,
        }


# Singleton instance
prompt_builder_service = PromptBuilderService()
