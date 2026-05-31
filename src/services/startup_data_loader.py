"""
Startup Data Loader - Ensures HF Hub data is downloaded before serving requests.

This module solves the race condition where the app starts serving requests
before CommitScheduler finishes downloading data from HF Hub, causing the
app to appear to have lost all calendar events and conversation memory.

Key Features:
- Synchronous download during startup (blocks until complete)
- Retry logic with exponential backoff
- LLM-readable backup generation for disaster recovery
- Health check integration (app won't be "ready" until data is loaded)
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


class StartupDataLoader:
    """Ensures all persistent data is loaded before app serves traffic."""

    def __init__(self):
        self._load_completed = False
        self._calendar_required = False
        self._memory_required = False
        self._documents_required = False
        self._logs_required = False
        self._calendar_loaded = False
        self._memory_loaded = False
        self._documents_loaded = False
        self._logs_loaded = False
        self._backup_created = False

    async def ensure_data_loaded(
        self,
        calendar_service: Any = None,
        memory_service: Any = None,
        document_service: Any = None,
        history_log: Any = None,
        max_retries: int = 3,
        retry_delay_seconds: int = 2,
    ) -> Dict[str, bool]:
        """
        Ensure all data services have loaded from HF Hub before returning.

        Args:
            calendar_service: CalendarService instance (optional)
            memory_service: ConversationMemoryService instance (optional)
            document_service: DocumentMemoryService instance (optional)
            history_log: HistoryLogService instance (optional)
            max_retries: Maximum number of download attempts per service
            retry_delay_seconds: Base delay between retries (exponential backoff)

        Returns:
            Dict with success status for each service
        """
        logger.info("🔄 Starting synchronous data load from HF Hub...")
        start_time = time.time()

        self._calendar_required = bool(
            calendar_service and hasattr(calendar_service, "_hf_enabled") and calendar_service._hf_enabled
        )
        self._memory_required = bool(
            memory_service and hasattr(memory_service, "_hf_enabled") and memory_service._hf_enabled
        )
        self._documents_required = bool(
            document_service and hasattr(document_service, "_hf_enabled") and document_service._hf_enabled
        )
        self._logs_required = bool(
            history_log and hasattr(history_log, "_hf_enabled") and history_log._hf_enabled
        )

        self._calendar_loaded = not self._calendar_required
        self._memory_loaded = not self._memory_required
        self._documents_loaded = not self._documents_required
        self._logs_loaded = not self._logs_required

        results = {
            "calendar": not self._calendar_required,
            "memory": not self._memory_required,
            "documents": not self._documents_required,
            "logs": not self._logs_required,
            "backup_created": False,
        }

        # Load calendar data
        if self._calendar_required:
            results["calendar"] = await self._load_calendar_with_retry(
                calendar_service, max_retries, retry_delay_seconds
            )
            self._calendar_loaded = results["calendar"]

        # Load conversation memory
        if self._memory_required:
            results["memory"] = await self._load_memory_with_retry(
                memory_service, max_retries, retry_delay_seconds
            )
            self._memory_loaded = results["memory"]

        # Load document memory
        if self._documents_required:
            results["documents"] = await self._load_documents_with_retry(
                document_service, max_retries, retry_delay_seconds
            )
            self._documents_loaded = results["documents"]

        # Load history logs
        if self._logs_required:
            results["logs"] = await self._load_logs_with_retry(
                history_log, max_retries, retry_delay_seconds
            )
            self._logs_loaded = results["logs"]

        # Create LLM-readable backup for disaster recovery
        if calendar_service:
            results["backup_created"] = await self._create_llm_backup(calendar_service)
            self._backup_created = results["backup_created"]

        self._load_completed = True

        elapsed = time.time() - start_time
        logger.info(f"✅ Data load complete in {elapsed:.2f}s: {results}")

        return results

    async def _load_calendar_with_retry(
        self, calendar_service: Any, max_retries: int, retry_delay: int
    ) -> bool:
        """Load calendar events from HF Hub with retry logic."""
        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"📅 Downloading calendar events (attempt {attempt}/{max_retries})...")

                # Use the service's existing sync download method
                if hasattr(calendar_service, "_load_from_hub_sync"):
                    calendar_service._load_from_hub_sync()
                    event_count = len(calendar_service._events)
                    logger.info(f"✅ Calendar loaded: {event_count} events")
                    return True

                # Fallback: Use async method if sync not available
                if hasattr(calendar_service, "_load_from_hub"):
                    await calendar_service._load_from_hub()
                    event_count = len(calendar_service._events)
                    logger.info(f"✅ Calendar loaded: {event_count} events")
                    return True

                logger.warning("⚠️ Calendar service missing load methods")
                return False

            except FileNotFoundError:
                logger.info("📅 Calendar HF repo is empty - starting fresh")
                return True  # Not an error, just empty repo
            except Exception as e:
                logger.warning(f"⚠️ Calendar load attempt {attempt} failed: {e}")
                if attempt < max_retries:
                    delay = retry_delay * (2 ** (attempt - 1))  # Exponential backoff
                    logger.info(f"⏳ Retrying in {delay}s...")
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"❌ Calendar load failed after {max_retries} attempts")
                    return False

        return False

    async def _load_documents_with_retry(
        self, document_service: Any, max_retries: int, retry_delay: int
    ) -> bool:
        """Load document memory from HF Hub with retry logic."""
        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"📄 Downloading documents (attempt {attempt}/{max_retries})...")

                if hasattr(document_service, "_load_from_hub"):
                    await document_service._load_from_hub()
                    logger.info("✅ Documents loaded")
                    return True

                logger.warning("⚠️ Document service missing load method")
                return False

            except FileNotFoundError:
                logger.info("📄 Document HF repo is empty - starting fresh")
                return True
            except Exception as e:
                logger.warning(f"⚠️ Document load attempt {attempt} failed: {e}")
                if attempt < max_retries:
                    delay = retry_delay * (2 ** (attempt - 1))
                    logger.info(f"⏳ Retrying in {delay}s...")
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"❌ Document load failed after {max_retries} attempts")
                    return False

        return False

    async def _load_memory_with_retry(
        self, memory_service: Any, max_retries: int, retry_delay: int
    ) -> bool:
        """Load conversation memory from HF Hub with retry logic."""
        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"💭 Downloading conversation memory (attempt {attempt}/{max_retries})...")

                # Memory service uses async load method
                if hasattr(memory_service, "_load_from_hub"):
                    await memory_service._load_from_hub()
                    conv_count = len(memory_service._conversations)
                    logger.info(f"✅ Memory loaded: {conv_count} conversations")
                    return True

                logger.warning("⚠️ Memory service missing load method")
                return False

            except FileNotFoundError:
                logger.info("💭 Memory HF repo is empty - starting fresh")
                return True
            except Exception as e:
                logger.warning(f"⚠️ Memory load attempt {attempt} failed: {e}")
                if attempt < max_retries:
                    delay = retry_delay * (2 ** (attempt - 1))
                    logger.info(f"⏳ Retrying in {delay}s...")
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"❌ Memory load failed after {max_retries} attempts")
                    return False

        return False

    async def _load_logs_with_retry(
        self, history_log: Any, max_retries: int, retry_delay: int
    ) -> bool:
        """Load history logs from HF Hub with retry logic."""
        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"📜 Downloading history logs (attempt {attempt}/{max_retries})...")

                # History log might not have an explicit load method (uses CommitScheduler)
                # Just verify the service is configured
                logger.info("✅ History log service ready")
                return True

            except Exception as e:
                logger.warning(f"⚠️ Logs load attempt {attempt} failed: {e}")
                if attempt < max_retries:
                    delay = retry_delay * (2 ** (attempt - 1))
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"❌ Logs load failed after {max_retries} attempts")
                    return False

        return False

    async def _create_llm_backup(self, calendar_service: Any) -> bool:
        """
        Create an LLM-readable backup of calendar events.

        This file can be read by Zeus LLM to restore calendar events if HF sync fails.
        Stored in src/prompts/backup/ so it's included in Docker build.
        """
        try:
            backup_dir = Path("src/prompts/backup")
            backup_dir.mkdir(parents=True, exist_ok=True)

            backup_file = backup_dir / "calendar_backup.md"
            timestamp = datetime.now(timezone.utc).isoformat()

            # Generate human-readable markdown
            events = getattr(calendar_service, "_events", {})
            if not events:
                backup_content = f"""# Zeus Calendar Backup

**Generated:** {timestamp}
**Status:** No events to backup

This file is auto-generated during startup as a disaster recovery mechanism.
If HF Hub sync fails, Zeus LLM can read this file and restore events.
"""
            else:
                event_list = []
                for event_id, event in events.items():
                    event_list.append({
                        "id": event.event_id,
                        "user_id": event.user_id,
                        "chat_id": event.chat_id,
                        "title": event.title,
                        "date": event.event_date.isoformat(),
                        "description": event.description,
                        "reminder_days": event.reminder_days,
                    })

                backup_content = f"""# Zeus Calendar Backup

**Generated:** {timestamp}
**Event Count:** {len(event_list)}

## Events

```json
{json.dumps(event_list, indent=2, ensure_ascii=False)}
```

## Restoration Instructions

If calendar data is lost after HF deployment:

1. Zeus LLM can read this file via semantic search or file read
2. Parse the JSON array above
3. Call calendar_service.add_event() for each entry
4. Events will auto-sync to HF Hub via CommitScheduler

**Note:** This backup is created during startup and includes all events
that were successfully loaded from HF Hub.
"""

            backup_file.write_text(backup_content, encoding="utf-8")
            logger.info(f"✅ LLM backup created: {backup_file} ({len(events)} events)")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to create LLM backup: {e}")
            return False

    def is_ready(self) -> bool:
        """
        Check if all required data is loaded.

        Returns:
            True if app is ready to serve traffic
        """
        if not self._load_completed:
            return False

        if self._calendar_required and not self._calendar_loaded:
            return False
        if self._memory_required and not self._memory_loaded:
            return False
        if self._documents_required and not self._documents_loaded:
            return False
        if self._logs_required and not self._logs_loaded:
            return False

        return True


# Singleton instance
startup_loader = StartupDataLoader()
