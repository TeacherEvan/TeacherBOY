"""Scheduler service for managing scheduled tasks using APScheduler."""

import logging
from typing import Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

logger = logging.getLogger(__name__)


class SchedulerService:
    """Service for managing scheduled background tasks."""

    def __init__(self):
        """Initialize the scheduler service."""
        self.scheduler: Optional[AsyncIOScheduler] = None
        self.timezone = pytz.timezone("Asia/Bangkok")  # Adjust timezone as needed

    def start(self):
        """Start the scheduler."""
        if self.scheduler is None:
            self.scheduler = AsyncIOScheduler(timezone=self.timezone)
            self.scheduler.start()
            logger.info("✅ Scheduler service started")
        else:
            logger.warning("⚠️  Scheduler already running")

    def stop(self):
        """Stop the scheduler."""
        if self.scheduler:
            self.scheduler.shutdown()
            self.scheduler = None
            logger.info("✅ Scheduler service stopped")

    def add_daily_job(self, func, hour: int, minute: int, name: str):
        """
        Add a daily scheduled job.

        Args:
            func: The async function to execute
            hour: Hour of day (0-23)
            minute: Minute of hour (0-59)
            name: Name/ID for the job
        """
        if not self.scheduler:
            logger.error("❌ Scheduler not started, cannot add job")
            return

        try:
            trigger = CronTrigger(hour=hour, minute=minute, timezone=self.timezone)
            self.scheduler.add_job(func, trigger=trigger, id=name, name=name, replace_existing=True)
            logger.info(f"✅ Scheduled daily job '{name}' at {hour:02d}:{minute:02d}")
        except Exception as e:
            logger.error(f"❌ Error adding scheduled job '{name}': {e}")

    def remove_job(self, name: str):
        """Remove a scheduled job by name."""
        if self.scheduler:
            try:
                self.scheduler.remove_job(name)
                logger.info(f"✅ Removed scheduled job '{name}'")
            except Exception as e:
                logger.error(f"❌ Error removing job '{name}': {e}")

    def list_jobs(self):
        """List all scheduled jobs."""
        if self.scheduler:
            jobs = self.scheduler.get_jobs()
            logger.info(f"📋 Scheduled jobs: {len(jobs)}")
            for job in jobs:
                logger.info(f"  - {job.name}: next run at {job.next_run_time}")
            return jobs
        return []


# Global scheduler instance
scheduler_service = SchedulerService()
