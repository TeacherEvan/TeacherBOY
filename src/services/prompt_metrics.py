"""Prompt Metrics Service - Track token usage and performance.

This service collects metrics about prompt optimization to help monitor
the effectiveness of the modular prompt system and conversation summarization.

Key metrics tracked:
- Token usage per prompt type (quick/standard/full)
- Response times for vision API calls
- Token savings from summarization
- Cost estimates
"""

import logging
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class PromptExecution:
    """Record of a single prompt execution."""

    prompt_type: str  # "quick", "standard", "full", "conversation"
    estimated_tokens: int
    actual_tokens: int | None = None  # From API response if available
    response_time_ms: float = 0.0
    model: str = "unknown"
    success: bool = True
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "prompt_type": self.prompt_type,
            "estimated_tokens": self.estimated_tokens,
            "actual_tokens": self.actual_tokens,
            "response_time_ms": self.response_time_ms,
            "model": self.model,
            "success": self.success,
            "timestamp": self.timestamp.isoformat(),
        }


class PromptMetricsCollector:
    """
    Collect and aggregate prompt optimization metrics.

    Thread-safe for concurrent agent operations.
    """

    def __init__(self, max_records: int = 1000):
        """
        Initialize metrics collector.

        Args:
            max_records: Maximum execution records to keep in memory
        """
        self._records: list[PromptExecution] = []
        self._max_records = max_records
        self._lock = threading.Lock()

        # Aggregated statistics
        self._token_usage_by_type: dict[str, list[int]] = defaultdict(list)
        self._response_times_by_type: dict[str, list[float]] = defaultdict(list)

        logger.info(f"📊 Prompt metrics collector initialized (max_records={max_records})")

    def record(self, execution: PromptExecution) -> None:
        """
        Record a prompt execution.

        Args:
            execution: Execution record to store
        """
        with self._lock:
            self._records.append(execution)

            # Update aggregated stats
            tokens = execution.actual_tokens or execution.estimated_tokens
            self._token_usage_by_type[execution.prompt_type].append(tokens)
            self._response_times_by_type[execution.prompt_type].append(execution.response_time_ms)

            # Trim old records if exceeded max
            if len(self._records) > self._max_records:
                removed = self._records.pop(0)
                logger.debug(f"📊 Removed oldest record ({removed.timestamp})")

        logger.debug(f"📊 Recorded {execution.prompt_type}: {tokens} tokens, {execution.response_time_ms:.0f}ms")

    def get_summary(self) -> dict:
        """
        Get summary statistics.

        Returns:
            Dictionary with aggregated metrics
        """
        with self._lock:
            summary = {
                "total_executions": len(self._records),
                "by_type": {},
            }

            for prompt_type, token_counts in self._token_usage_by_type.items():
                if not token_counts:
                    continue

                response_times = self._response_times_by_type[prompt_type]

                summary["by_type"][prompt_type] = {
                    "count": len(token_counts),
                    "avg_tokens": sum(token_counts) / len(token_counts),
                    "min_tokens": min(token_counts),
                    "max_tokens": max(token_counts),
                    "avg_response_ms": sum(response_times) / len(response_times) if response_times else 0,
                }

            # Calculate token savings if we have both optimized and legacy
            if "standard" in summary["by_type"] and "legacy" in summary["by_type"]:
                optimized_avg = summary["by_type"]["standard"]["avg_tokens"]
                legacy_avg = summary["by_type"]["legacy"]["avg_tokens"]
                savings_pct = ((legacy_avg - optimized_avg) / legacy_avg) * 100

                summary["token_savings_percent"] = round(savings_pct, 1)

            return summary

    def get_recent_executions(self, limit: int = 10) -> list[dict]:
        """
        Get recent execution records.

        Args:
            limit: Number of recent records to return

        Returns:
            List of execution records as dictionaries
        """
        with self._lock:
            recent = self._records[-limit:]
            return [r.to_dict() for r in reversed(recent)]

    def estimate_cost_savings(self, vision_cost_per_1k: float = 0.01, llm_cost_per_1k: float = 0.001) -> dict:
        """
        Estimate cost savings from optimizations.

        Args:
            vision_cost_per_1k: Cost per 1000 tokens for vision API
            llm_cost_per_1k: Cost per 1000 tokens for LLM API

        Returns:
            Dictionary with cost analysis
        """
        with self._lock:
            vision_types = ["quick", "standard", "full"]
            conversation_types = ["conversation", "conversation_summarized"]

            vision_tokens_total = 0
            llm_tokens_total = 0

            for prompt_type, token_counts in self._token_usage_by_type.items():
                total = sum(token_counts)

                if prompt_type in vision_types:
                    vision_tokens_total += total
                elif prompt_type in conversation_types:
                    llm_tokens_total += total

            vision_cost = (vision_tokens_total / 1000) * vision_cost_per_1k
            llm_cost = (llm_tokens_total / 1000) * llm_cost_per_1k
            total_cost = vision_cost + llm_cost

            return {
                "vision_tokens": vision_tokens_total,
                "vision_cost_usd": round(vision_cost, 2),
                "llm_tokens": llm_tokens_total,
                "llm_cost_usd": round(llm_cost, 2),
                "total_cost_usd": round(total_cost, 2),
                "executions": len(self._records),
            }

    def log_summary(self) -> None:
        """Log summary statistics to console."""
        summary = self.get_summary()

        logger.info("📊 ═══════════ Prompt Metrics Summary ═══════════")
        logger.info(f"📊 Total executions: {summary['total_executions']}")

        for prompt_type, stats in summary.get("by_type", {}).items():
            logger.info(
                f"📊 {prompt_type:20s}: "
                f"{stats['count']:3d} calls, "
                f"avg {stats['avg_tokens']:6.0f} tokens, "
                f"avg {stats['avg_response_ms']:6.0f}ms"
            )

        if "token_savings_percent" in summary:
            logger.info(f"📊 Token savings: {summary['token_savings_percent']}%")

        cost_estimate = self.estimate_cost_savings()
        if cost_estimate["executions"] > 0:
            logger.info(
                f"📊 Estimated cost: ${cost_estimate['total_cost_usd']:.2f} "
                f"({cost_estimate['vision_tokens']:,} vision + {cost_estimate['llm_tokens']:,} LLM tokens)"
            )

        logger.info("📊 ═══════════════════════════════════════════════")

    def reset(self) -> None:
        """Clear all collected metrics."""
        with self._lock:
            self._records.clear()
            self._token_usage_by_type.clear()
            self._response_times_by_type.clear()

        logger.info("📊 Metrics reset")


# Global singleton instance
metrics_collector = PromptMetricsCollector()
