"""
Reminder Service - Scheduled notification delivery for calendar events.

Runs a daily job at 8AM Bangkok time to check for events needing reminders.
Sends LINE push messages directly to users (if friend) or to the group/room.

Uses APScheduler via the existing scheduler_service.py pattern.
"""

import asyncio
import logging
from datetime import datetime, date, timezone, timedelta
from typing import Optional, List, Dict, Any
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# Bangkok timezone
BANGKOK_TZ = ZoneInfo("Asia/Bangkok")


class ReminderService:
    """
    Service for checking and sending calendar reminders.
    
    Integrates with:
    - CalendarService: Get events needing reminders
    - LINE Messaging API: Send push notifications
    - SchedulerService: Run daily at configured hour
    """

    def __init__(self):
        """Initialize reminder service."""
        self._line_bot_api: Optional[Any] = None
        self._calendar_service: Optional[Any] = None
        self._scheduler_job_id: Optional[str] = None
        self._reminder_hour: int = 8  # Default 8 AM Bangkok
        self._enabled: bool = True

    def configure(
        self,
        line_bot_api: Optional[Any] = None,
        calendar_service: Optional[Any] = None,
        reminder_hour: int = 8,
        enabled: bool = True
    ) -> None:
        """
        Configure the reminder service with dependencies.

        Args:
            line_bot_api: LINE MessagingApi instance (optional, can set later via start())
            calendar_service: CalendarService instance (optional, can set later via start())
            reminder_hour: Hour of day (0-23) in Bangkok timezone
            enabled: Whether reminders are enabled
        """
        if line_bot_api is not None:
            self._line_bot_api = line_bot_api
        if calendar_service is not None:
            self._calendar_service = calendar_service
        self._reminder_hour = reminder_hour
        self._enabled = enabled
        
        logger.info(
            f"⏰ ReminderService configured: hour={reminder_hour}, enabled={enabled}"
        )

    def start_scheduler(self, scheduler_service: Any) -> None:
        """
        Register the daily reminder job with the scheduler.

        Args:
            scheduler_service: SchedulerService instance
        """
        if not self._enabled:
            logger.info("⏰ Reminders disabled, not scheduling job")
            return

        # Create a cron trigger for daily at the configured hour (Bangkok time)
        try:
            from apscheduler.triggers.cron import CronTrigger
            
            trigger = CronTrigger(
                hour=self._reminder_hour,
                minute=0,
                timezone=BANGKOK_TZ
            )
            
            self._scheduler_job_id = scheduler_service.add_job(
                func=self._check_and_send_reminders,
                trigger=trigger,
                id="calendar_reminder_check",
                name="Calendar Reminder Check",
                replace_existing=True
            )
            
            logger.info(
                f"⏰ Scheduled daily reminder check at {self._reminder_hour}:00 Bangkok time"
            )
            
        except ImportError:
            logger.error("❌ APScheduler not available for reminder scheduling")
        except Exception as e:
            logger.error(f"❌ Failed to schedule reminder job: {e}", exc_info=True)

    def stop_scheduler(self, scheduler_service: Any) -> None:
        """
        Remove the reminder job from scheduler.

        Args:
            scheduler_service: SchedulerService instance
        """
        if self._scheduler_job_id:
            try:
                scheduler_service.remove_job(self._scheduler_job_id)
                logger.info("⏰ Removed reminder scheduler job")
            except Exception as e:
                logger.warning(f"⚠️ Failed to remove reminder job: {e}")
            finally:
                self._scheduler_job_id = None

    async def _check_and_send_reminders(self) -> None:
        """
        Check all events for reminders due today and send notifications.
        
        This is the main scheduled job that runs daily.
        """
        if not self._enabled or not self._calendar_service:
            return

        logger.info("⏰ Starting daily reminder check...")
        
        try:
            # Get today's date in Bangkok timezone
            today = datetime.now(BANGKOK_TZ).date()
            
            # Get all events needing reminders
            events_needing_reminder = await self._calendar_service.get_events_needing_reminder(today)
            
            if not events_needing_reminder:
                logger.info("⏰ No reminders to send today")
                return
            
            logger.info(f"⏰ Found {len(events_needing_reminder)} reminders to send")
            
            # Send each reminder
            sent_count = 0
            for event_data in events_needing_reminder:
                event = event_data["event"]
                days_until = event_data["days_until"]
                
                try:
                    success = await self._send_reminder(event, days_until)
                    if success:
                        # Mark as notified
                        await self._calendar_service.mark_event_notified(
                            event.event_id,
                            today
                        )
                        sent_count += 1
                except Exception as e:
                    logger.error(
                        f"❌ Failed to send reminder for event {event.event_id}: {e}"
                    )
            
            logger.info(f"⏰ Sent {sent_count}/{len(events_needing_reminder)} reminders")
            
        except Exception as e:
            logger.error(f"❌ Error in reminder check: {e}", exc_info=True)

    async def _send_reminder(
        self, 
        event: Any,  # CalendarEvent
        days_until: int
    ) -> bool:
        """
        Send a reminder notification for an event.

        Args:
            event: CalendarEvent object
            days_until: Days until event (0 = today)

        Returns:
            True if sent successfully
        """
        if not self._line_bot_api:
            logger.warning("⚠️ LINE API not configured, cannot send reminder")
            return False

        # Format the reminder message
        message_text = self._format_reminder_message(event, days_until)
        
        # Determine where to send
        # If user is friend, send DM. Otherwise, send to original chat (group/room)
        if event.is_friend:
            # Send as DM to user
            target = event.user_id
            logger.info(f"⏰ Sending DM reminder to user {target}")
        else:
            # Send to original chat (group/room/user)
            # Extract the actual ID from chat_id format (group_xxx, room_xxx, user_xxx)
            chat_id = event.chat_id
            if chat_id.startswith("group_"):
                target = chat_id[6:]  # Remove "group_" prefix
            elif chat_id.startswith("room_"):
                target = chat_id[5:]  # Remove "room_" prefix
            elif chat_id.startswith("user_"):
                target = chat_id[5:]  # Remove "user_" prefix
            else:
                target = chat_id
            logger.info(f"⏰ Sending reminder to chat {target}")

        try:
            from linebot.v3.messaging import PushMessageRequest, TextMessage
            
            text_msg = TextMessage(
                text=message_text,
                quickReply=None,
                quoteToken=None
            )
            
            request = PushMessageRequest(
                to=target,
                messages=[text_msg],
                notificationDisabled=False,
            )
            
            await asyncio.to_thread(
                self._line_bot_api.push_message,
                request
            )
            
            logger.info(f"✅ Sent reminder for '{event.title}' ({days_until} days)")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to send LINE push: {e}", exc_info=True)
            return False

    def _format_reminder_message(
        self, 
        event: Any,  # CalendarEvent
        days_until: int
    ) -> str:
        """
        Format the reminder message text.

        Args:
            event: CalendarEvent object
            days_until: Days until event

        Returns:
            Formatted message string
        """
        # Format date
        date_str = event.event_date.strftime("%b %d, %Y")
        
        # Build message based on urgency
        if days_until == 0:
            # Today - most urgent
            header = "🔔 TODAY"
            urgency_emoji = "🚨"
            time_text = "is TODAY"
        elif days_until == 1:
            # Tomorrow
            header = "⏰ TOMORROW"
            urgency_emoji = "⚠️"
            time_text = "is TOMORROW"
        elif days_until <= 3:
            # 2-3 days
            header = f"⏰ In {days_until} days"
            urgency_emoji = "📅"
            time_text = f"in {days_until} days"
        else:
            # 4+ days (typically 7)
            header = f"📆 In {days_until} days"
            urgency_emoji = "📌"
            time_text = f"in {days_until} days"

        # Build message
        lines = [
            f"{header}",
            "",
            f"{urgency_emoji} {event.title}",
            f"📅 {date_str} ({time_text})",
        ]
        
        # Add description if present
        if event.description:
            lines.append("")
            lines.append(f"📝 {event.description}")
        
        # Add Thai translation for key parts
        if days_until == 0:
            lines.append("")
            lines.append("วันนี้! อย่าลืมนะคะ 😊")
        elif days_until == 1:
            lines.append("")
            lines.append("พรุ่งนี้แล้ว! เตรียมตัวด้วยนะคะ")
        
        return "\n".join(lines)

    async def send_immediate_reminder(
        self,
        event: Any,  # CalendarEvent
        days_until: int,
        target_id: str
    ) -> bool:
        """
        Send an immediate reminder (for testing or manual trigger).

        Args:
            event: CalendarEvent object
            days_until: Days until event
            target_id: LINE user/group/room ID

        Returns:
            True if sent successfully
        """
        if not self._line_bot_api:
            return False

        message_text = self._format_reminder_message(event, days_until)
        
        try:
            from linebot.v3.messaging import PushMessageRequest, TextMessage
            
            text_msg = TextMessage(
                text=message_text,
                quickReply=None,
                quoteToken=None
            )
            
            request = PushMessageRequest(
                to=target_id,
                messages=[text_msg],
                notificationDisabled=False,
            )
            
            await asyncio.to_thread(
                self._line_bot_api.push_message,
                request
            )
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to send immediate reminder: {e}")
            return False

    async def check_reminders_manually(self) -> Dict[str, Any]:
        """
        Manually trigger reminder check (for admin/testing).

        Returns:
            Dict with check results
        """
        if not self._calendar_service:
            return {"error": "Calendar service not configured"}

        today = datetime.now(BANGKOK_TZ).date()
        events_needing_reminder = await self._calendar_service.get_events_needing_reminder(today)
        
        return {
            "date": today.isoformat(),
            "reminders_due": len(events_needing_reminder),
            "events": [
                {
                    "event_id": e["event"].event_id,
                    "title": e["event"].title,
                    "event_date": e["event"].event_date.isoformat(),
                    "days_until": e["days_until"],
                    "is_friend": e["event"].is_friend,
                }
                for e in events_needing_reminder
            ]
        }

    def get_next_run_time(self) -> Optional[datetime]:
        """Get the next scheduled run time."""
        # Calculate next run based on current time and configured hour
        now = datetime.now(BANGKOK_TZ)
        
        next_run = now.replace(
            hour=self._reminder_hour,
            minute=0,
            second=0,
            microsecond=0
        )
        
        # If we've passed today's run time, schedule for tomorrow
        if now >= next_run:
            next_run += timedelta(days=1)
        
        return next_run


# Singleton instance
reminder_service = ReminderService()
