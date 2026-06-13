"""
Memory Monitor Service - HF Spaces memory pressure monitoring.

Monitors container memory usage and triggers auto-flush when pressure is critical.
"""

import logging
import os
from enum import StrEnum

logger = logging.getLogger(__name__)


class MemoryPressure(StrEnum):
    """Memory pressure levels."""

    LOW = "low"  # < 50% used
    MEDIUM = "medium"  # 50-75% used
    HIGH = "high"  # 75-90% used
    CRITICAL = "critical"  # > 90% used


class MemoryMonitorService:
    """Monitors container memory and provides pressure level."""

    # Order for comparison: LOW < MEDIUM < HIGH < CRITICAL
    _PRESSURE_ORDER = {
        MemoryPressure.LOW: 0,
        MemoryPressure.MEDIUM: 1,
        MemoryPressure.HIGH: 2,
        MemoryPressure.CRITICAL: 3,
    }

    def __init__(
        self,
        check_interval_seconds: int = 60,
        auto_flush_threshold: str = "CRITICAL",
        auto_flush_mode: str = "time_based",
        auto_flush_days: int = 7,
    ):
        self.check_interval_seconds = check_interval_seconds
        self.auto_flush_threshold = MemoryPressure(auto_flush_threshold.lower())
        self.auto_flush_mode = auto_flush_mode
        self.auto_flush_days = auto_flush_days
        self._memory_limit_bytes: int | None = None
        self._last_check: float = 0

    def get_memory_limit_bytes(self) -> int | None:
        """Get memory limit from cgroup (HF Spaces/Docker).

        Note: Does NOT fall back to psutil.virtual_memory() because that returns
        host system memory, not the container's cgroup limit.
        """
        if self._memory_limit_bytes is not None:
            return self._memory_limit_bytes

        # Try cgroup v2 first
        cgroup_paths = [
            "/sys/fs/cgroup/memory.max",
            "/sys/fs/cgroup/memory.limit_in_bytes",  # cgroup v1
        ]

        for path in cgroup_paths:
            try:
                with open(path) as f:
                    content = f.read().strip()
                    if content and content != "max":
                        limit = int(content)
                        if limit > 0:
                            self._memory_limit_bytes = limit
                            logger.debug(f"📊 Memory limit detected: {limit / (1024**3):.2f} GB")
                            return self._memory_limit_bytes
            except (OSError, ValueError):
                continue

        logger.warning("⚠️ Could not detect container memory limit from cgroup")
        return None

    def get_memory_usage_bytes(self) -> int:
        """Get current memory usage."""
        try:
            import psutil

            process = psutil.Process(os.getpid())
            return process.memory_info().rss
        except ImportError:
            # Fallback: read from /proc/self/status
            try:
                with open("/proc/self/status") as f:
                    for line in f:
                        if line.startswith("VmRSS:"):
                            # VmRSS is in kB
                            return int(line.split()[1]) * 1024
            except (OSError, ValueError):
                pass
        return 0

    def get_memory_pressure(self) -> MemoryPressure:
        """Calculate memory pressure level."""
        limit = self.get_memory_limit_bytes()
        if not limit:
            return MemoryPressure.LOW

        usage = self.get_memory_usage_bytes()
        if usage == 0:
            return MemoryPressure.LOW

        pct = (usage / limit) * 100

        if pct >= 90:
            return MemoryPressure.CRITICAL
        elif pct >= 75:
            return MemoryPressure.HIGH
        elif pct >= 50:
            return MemoryPressure.MEDIUM
        else:
            return MemoryPressure.LOW

    def get_memory_info(self) -> dict:
        """Get detailed memory information."""
        limit = self.get_memory_limit_bytes()
        usage = self.get_memory_usage_bytes()
        pressure = self.get_memory_pressure()
        pct = (usage / limit * 100) if limit and usage else 0

        return {
            "limit_bytes": limit,
            "usage_bytes": usage,
            "usage_percent": round(pct, 1),
            "pressure": pressure.value,
            "auto_flush_threshold": self.auto_flush_threshold.value,
            "auto_flush_mode": self.auto_flush_mode,
            "auto_flush_days": self.auto_flush_days,
        }

    def should_auto_flush(self) -> bool:
        """Check if auto-flush should be triggered."""
        current = self.get_memory_pressure()
        return self._PRESSURE_ORDER[current] >= self._PRESSURE_ORDER[self.auto_flush_threshold]


# Global instance
_memory_monitor: MemoryMonitorService | None = None


def get_memory_monitor() -> MemoryMonitorService | None:
    """Get the memory monitor instance."""
    return _memory_monitor


def init_memory_monitor(
    check_interval_seconds: int = 60,
    auto_flush_threshold: str = "CRITICAL",
    auto_flush_mode: str = "time_based",
    auto_flush_days: int = 7,
) -> MemoryMonitorService:
    """Initialize the memory monitor service."""
    global _memory_monitor

    _memory_monitor = MemoryMonitorService(
        check_interval_seconds=check_interval_seconds,
        auto_flush_threshold=auto_flush_threshold,
        auto_flush_mode=auto_flush_mode,
        auto_flush_days=auto_flush_days,
    )

    logger.info(f"📊 Memory Monitor initialized (threshold: {auto_flush_threshold}, mode: {auto_flush_mode})")
    return _memory_monitor


async def check_and_auto_flush() -> bool:
    """
    Check memory pressure and trigger auto-flush if needed.

    Returns:
        True if flush was triggered, False otherwise
    """
    monitor = get_memory_monitor()
    if not monitor:
        return False

    if monitor.should_auto_flush():
        logger.warning(f"🚨 Memory pressure {monitor.get_memory_pressure().value} - triggering auto-flush")

        # Import here to avoid circular dependency
        from src.services.conversation_memory_service import FlushMode, FlushParams, get_conversation_memory
        from src.services.document_memory_service import FlushMode as DocFlushMode
        from src.services.document_memory_service import FlushParams as DocFlushParams
        from src.services.document_memory_service import get_document_memory

        conv_memory = get_conversation_memory()
        doc_memory = get_document_memory()

        flush_triggered = False

        if conv_memory:
            params = FlushParams(older_than_days=monitor.auto_flush_days, dry_run=False)
            conv_result = await conv_memory.flush_memory(FlushMode(monitor.auto_flush_mode), params)
            logger.info(f"🧹 Auto-flush conversations: {conv_result}")
            flush_triggered = True

        if doc_memory:
            doc_params = DocFlushParams(older_than_days=monitor.auto_flush_days, dry_run=False)
            doc_result = await doc_memory.purge_documents(DocFlushMode(monitor.auto_flush_mode), doc_params)
            logger.info(f"🧹 Auto-flush documents: {doc_result}")
            flush_triggered = True

        return flush_triggered

    return False
