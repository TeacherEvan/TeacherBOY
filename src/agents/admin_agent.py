"""Admin agent - Handles admin control commands for bot management."""

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING
import httpx
from linebot.v3.webhooks import MessageEvent
from linebot.v3.messaging import (
    MessagingApi,
    ReplyMessageRequest,
    PushMessageRequest,
    TextMessage,
)

if TYPE_CHECKING:
    from src.services.news_data_service import NewsDataService

from .base_agent import BaseAgent
from src.services.session_manager import session_manager
from src.services.rate_limiter import rate_limiter
from src.services.metrics_service import metrics_service
from src.services.admin_confirmation_service import admin_confirmation_service
from src.config import settings

logger = logging.getLogger(__name__)


class AdminAgent(BaseAgent):
    """Agent for handling admin control commands."""

    def __init__(
        self,
        http_client: Optional[httpx.AsyncClient] = None,
        news_api_key: str | None = None,
        news_data_service: Optional["NewsDataService"] = None,
    ):
        super().__init__(
            name="AdminAgent",
            description="Admin commands for bot management and control",
        )
        self._http_client = http_client
        self._news_data_service = news_data_service
        self._admin_user_ids = settings.get_admin_user_ids()
        self._admin_setup_key = (
            settings.admin_setup_key.strip()
            if isinstance(settings.admin_setup_key, str)
            else None
        )
        self._claimed_admin_user_id: str | None = None

        if self._admin_user_ids:
            logger.info(
                f"✅ AdminAgent initialized with {len(self._admin_user_ids)} authorized admin(s)"
            )
        else:
            logger.warning(
                "⚠️  AdminAgent initialized but no admin users configured (ADMIN_USER_IDS)"
            )

    def get_priority(self) -> int:
        """Admin commands have highest priority (lower number = higher priority)."""
        return 5

    def _is_admin(self, user_id: str) -> bool:
        """Check if user is authorized as admin."""
        if not self._admin_user_ids:
            return False
        return user_id in self._admin_user_ids

    def _is_admin_command(self, text: str) -> bool:
        """Check if text is an admin command."""
        text_lower = text.lower().strip()

        if text_lower.startswith("/admin") or text_lower.startswith("!admin"):
            return True

        teacher_pattern = r"teacher(?:boy|boi|biy|boj|boii)"
        return bool(re.match(rf"^{teacher_pattern}\s+admin\b", text_lower))

    def _parse_admin_command(self, text: str) -> tuple[str | None, str | None]:
        """Parse an admin command into (cmd, args).

        Supported formats:
        - /admin <cmd> [args...]
        - !admin <cmd> [args...]
        - TeacherBoy admin <cmd> [args...]
        """
        raw = text.strip()
        raw_lower = raw.lower()

        if raw_lower.startswith("/admin") or raw_lower.startswith("!admin"):
            parts = raw.split(maxsplit=2)
            if len(parts) < 2:
                return None, None
            cmd = parts[1].lower()
            arg = parts[2] if len(parts) > 2 else None
            return cmd, arg

        teacher_pattern = r"teacher(?:boy|boi|biy|boj|boii)"
        match = re.match(
            rf"^\s*(?P<teacher>{teacher_pattern})\s+admin(?:\s+(?P<rest>.*))?$",
            raw,
            flags=re.IGNORECASE,
        )
        if not match:
            return None, None

        rest = (match.group("rest") or "").strip()
        if not rest:
            return None, None

        parts = rest.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else None
        return cmd, arg

    async def should_handle(self, event: MessageEvent, text: str) -> bool:
        """Handle if message is an admin command from an authorized user (or bootstrap claim)."""
        if not self._is_admin_command(text):
            return False

        # Get user ID from event
        user_id = getattr(event.source, "user_id", None) if event.source else None
        if not user_id:
            return False

        # Allow bootstrap claim when configured (even if user isn't an admin yet)
        cmd, _ = self._parse_admin_command(text)
        if cmd == "claim" and self._admin_setup_key:
            return True

        return self._is_admin(user_id)

    async def handle(
        self, event: MessageEvent, text: str, line_bot_api: MessagingApi
    ) -> bool:
        """Process admin command."""
        chat_id = self._get_chat_id(event)
        user_id = getattr(event.source, "user_id", None) if event.source else None

        try:
            # Parse command
            cmd, arg = self._parse_admin_command(text)
            if not cmd:
                # Just "/admin" or "!admin" - show help
                response = self._get_help_message()
            else:
                command = cmd

                # Bootstrap: /admin claim <key>
                if command == "claim":
                    response = self._claim_admin(user_id, chat_id, arg)
                # Normal admin commands

                # Execute command
                elif command == "help":
                    response = self._get_help_message()
                elif command == "stats":
                    response = await self._get_stats_message(line_bot_api)
                elif command == "confirm":
                    response = await self._confirm_action(
                        chat_id, user_id, arg, line_bot_api
                    )
                elif command == "cancel":
                    response = self._cancel_action(chat_id, user_id, arg)
                elif command == "status":
                    response = self._get_status_message(chat_id, arg)
                elif command == "wake":
                    response = self._wake_chat(chat_id, arg)
                elif command == "sleep":
                    response = self._sleep_chat(chat_id, arg)
                elif command == "reset":
                    response = self._reset_chat(chat_id, arg)
                elif command == "purge":
                    response = await self._request_confirm_purge(
                        event, line_bot_api, chat_id, user_id, arg
                    )
                elif command == "leave":
                    response = await self._request_confirm_leave(
                        event, line_bot_api, chat_id, user_id, arg
                    )
                elif command == "sessions":
                    response = self._list_sessions()
                else:
                    response = (
                        f"❌ Unknown command: {command}\n\n"
                        "Use TeacherBoy admin help (or /admin help) for available commands."
                    )

            # Send response
            if event.reply_token:
                await asyncio.to_thread(
                    line_bot_api.reply_message,
                    ReplyMessageRequest(
                        replyToken=event.reply_token,
                        messages=[
                            TextMessage(text=response, quickReply=None, quoteToken=None)
                        ],
                        notificationDisabled=False,
                    ),
                )

            # Record admin command execution
            metrics_service.record_admin_command()
            logger.info(
                f"🔧 Admin command executed by {user_id} in chat {chat_id}: {text}"
            )
            return True

        except Exception as e:
            logger.error(f"❌ Admin agent error: {e}", exc_info=True)

            # Send error message
            if event.reply_token:
                await asyncio.to_thread(
                    line_bot_api.reply_message,
                    ReplyMessageRequest(
                        replyToken=event.reply_token,
                        messages=[
                            TextMessage(
                                text=f"❌ Error executing command: {str(e)}\n\nUse /admin help for usage.",
                                quickReply=None,
                                quoteToken=None,
                            )
                        ],
                        notificationDisabled=False,
                    ),
                )
            return False

    def _claim_admin(self, user_id: str | None, chat_id: str, arg: str | None) -> str:
        """Allow one-time admin bootstrap using ADMIN_SETUP_KEY."""
        if not self._admin_setup_key:
            return (
                "❌ Admin bootstrap is not enabled.\n\n"
                "Ask the deployer to set ADMIN_SETUP_KEY, then run: /admin claim <key>"
            )

        if not user_id:
            return "❌ Could not determine your LINE user ID from this event."

        provided_key = (arg or "").strip()
        if not provided_key:
            return "Usage: /admin claim <ADMIN_SETUP_KEY>"

        if provided_key != self._admin_setup_key:
            logger.warning(
                f"⚠️  Invalid admin claim attempt from user {user_id} in {chat_id}"
            )
            return "❌ Invalid claim key."

        if self._claimed_admin_user_id and self._claimed_admin_user_id != user_id:
            return (
                "❌ Admin was already claimed for this running instance.\n\n"
                "Persist admin via ADMIN_USER_IDS in your host settings, then restart."
            )

        # Grant in-memory admin for this process so user can immediately use /admin commands
        if user_id not in self._admin_user_ids:
            self._admin_user_ids.append(user_id)
        self._claimed_admin_user_id = user_id

        return (
            "✅ Admin claim successful (for this running instance).\n\n"
            f"Your LINE user ID: {user_id}\n"
            f"This chat ID: {chat_id}\n\n"
            "To make it permanent:\n"
            f"- Set ADMIN_USER_IDS={user_id} in your host environment\n"
            "- Restart the service\n"
            "- Remove ADMIN_SETUP_KEY afterwards"
        )

    def _get_help_message(self) -> str:
        """Get help message with all available admin commands."""
        return (
            "🔧 Admin Commands\n"
            "━━━━━━━━━━━━━━━━\n\n"
            "You can run commands as:\n"
            "  TeacherBoy admin <command>\n"
            "  /admin <command>\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "📊 Status & Info:\n"
            "━━━━━━━━━━━━━━━━\n"
            "  /admin status [chat_id]\n"
            "    → Show current chat status\n\n"
            "  /admin stats\n"
            "    → Show service stats dashboard\n\n"
            "  /admin sessions\n"
            "    → List all active sessions\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "🚪 Leave Chats:\n"
            "━━━━━━━━━━━━━━━━\n"
            "  /admin leave\n"
            "    → Request leaving current group/room (confirmation required)\n\n"
            "  /admin leave <chat_id>\n"
            "    → Request leaving a specific group/room (confirmation required)\n\n"
            "  /admin leave group <group_id>\n"
            "  /admin leave room <room_id>\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "😴 Sleep Management:\n"
            "━━━━━━━━━━━━━━━━\n"
            "  /admin sleep [chat_id] [hours]\n"
            "    → Put chat to sleep (default: 24h)\n\n"
            "  /admin wake [chat_id]\n"
            "    → Wake sleeping chat\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "🔄 Session Control:\n"
            "━━━━━━━━━━━━━━━━\n"
            "  /admin reset [chat_id]\n"
            "    → Reset chat session & history\n\n"
            "  /admin purge [chat_id]\n"
            "    → Request clearing bot internal history/state for a chat\n"
            "      (Note: LINE does not support deleting/unsending chat messages via API)\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "✅ Confirmations (private chat only):\n"
            "━━━━━━━━━━━━━━━━\n"
            "  /admin confirm <token>\n"
            "  /admin cancel <token>\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "💡 Tips:\n"
            "━━━━━━━━━━━━━━━━\n"
            "• [chat_id] is optional - defaults to current chat\n"
            "• Chat IDs format: user_U123..., group_C123...\n"
            "• Use 'sessions' to see active chat IDs"
        )

    def _is_private_chat(self, chat_id: str) -> bool:
        return chat_id.startswith("user_")

    def _mask_user_id(self, user_id: str | None) -> str:
        if not user_id:
            return "N/A"
        if len(user_id) <= 6:
            return user_id
        return f"{user_id[:3]}…{user_id[-3:]}"

    def _push_to_admin(
        self, line_bot_api: MessagingApi, user_id: str, text: str
    ) -> bool:
        """Best-effort push message to admin's private chat."""
        try:
            if not hasattr(line_bot_api, "push_message"):
                return False
            line_bot_api.push_message(
                PushMessageRequest(
                    to=user_id,
                    messages=[TextMessage(text=text, quickReply=None, quoteToken=None)],
                    notificationDisabled=False,
                    customAggregationUnits=[],
                )
            )
            return True
        except Exception:
            return False

    async def _request_confirm_leave(
        self,
        event: MessageEvent,
        line_bot_api: MessagingApi,
        current_chat_id: str,
        user_id: str | None,
        arg: str | None,
    ) -> str:
        if not user_id:
            return "❌ Could not determine your LINE user ID."

        kind, target_id, error = self._parse_leave_target(current_chat_id, arg)
        if error or not kind or not target_id:
            return error or "❌ Could not determine leave target."

        pending = admin_confirmation_service.create(
            action="leave",
            requested_by_user_id=user_id,
            requested_from_chat_id=current_chat_id,
            payload={"kind": kind, "target_id": target_id},
        )

        confirm_text = (
            "🔐 Confirm admin action\n"
            "━━━━━━━━━━━━━━━━\n\n"
            f"Action: leave {kind} {target_id}\n"
            f"Token: {pending.token}\n"
            f"Expires: {pending.expires_at.strftime('%H:%M:%S')} UTC\n\n"
            f"Confirm: /admin confirm {pending.token}\n"
            f"Cancel: /admin cancel {pending.token}"
        )

        pushed = await asyncio.to_thread(
            self._push_to_admin, line_bot_api, user_id, confirm_text
        )
        if pushed:
            return "✅ Confirmation sent to your private chat."

        # Fallback when push isn't available.
        return (
            "⚠️ Could not push a private confirmation message.\n\n"
            f"Confirm here (preferred in private chat): /admin confirm {pending.token}\n"
            f"Cancel: /admin cancel {pending.token}"
        )

    async def _request_confirm_purge(
        self,
        event: MessageEvent,
        line_bot_api: MessagingApi,
        current_chat_id: str,
        user_id: str | None,
        arg: str | None,
    ) -> str:
        if not user_id:
            return "❌ Could not determine your LINE user ID."

        target_chat_id = (arg or "").strip() or current_chat_id
        pending = admin_confirmation_service.create(
            action="purge",
            requested_by_user_id=user_id,
            requested_from_chat_id=current_chat_id,
            payload={"chat_id": target_chat_id},
        )

        confirm_text = (
            "🔐 Confirm admin action\n"
            "━━━━━━━━━━━━━━━━\n\n"
            f"Action: purge {target_chat_id}\n"
            f"Token: {pending.token}\n"
            f"Expires: {pending.expires_at.strftime('%H:%M:%S')} UTC\n\n"
            f"Confirm: /admin confirm {pending.token}\n"
            f"Cancel: /admin cancel {pending.token}"
        )

        pushed = await asyncio.to_thread(
            self._push_to_admin, line_bot_api, user_id, confirm_text
        )
        if pushed:
            return "✅ Confirmation sent to your private chat."

        return (
            "⚠️ Could not push a private confirmation message.\n\n"
            f"Confirm here (preferred in private chat): /admin confirm {pending.token}\n"
            f"Cancel: /admin cancel {pending.token}"
        )

    async def _confirm_action(
        self,
        chat_id: str,
        user_id: str | None,
        arg: str | None,
        line_bot_api: MessagingApi,
    ) -> str:
        if not user_id:
            return "❌ Could not determine your LINE user ID."

        token = (arg or "").strip()
        if not token:
            return "Usage: /admin confirm <token>"

        # Enforce private-chat confirmation.
        if not self._is_private_chat(chat_id):
            return "❌ Please confirm in your private chat with the bot."

        pending, msg = admin_confirmation_service.confirm(token, user_id)
        if not pending:
            return msg

        if pending.action == "leave":
            kind = str(pending.payload.get("kind"))
            target_id = str(pending.payload.get("target_id"))
            try:
                if kind == "group":
                    await asyncio.to_thread(line_bot_api.leave_group, target_id)
                else:
                    await asyncio.to_thread(line_bot_api.leave_room, target_id)
                return f"✅ Left {kind} {target_id}."
            except Exception as e:
                logger.error(
                    f"❌ Failed to leave {kind} {target_id}: {e}", exc_info=True
                )
                return f"❌ Failed to leave {kind} {target_id}."

        if pending.action == "purge":
            target_chat_id = str(pending.payload.get("chat_id"))
            return self._purge_chat(
                current_chat_id=chat_id, target_chat_id=target_chat_id
            )

        return "❌ Unknown pending action type."

    def _cancel_action(self, chat_id: str, user_id: str | None, arg: str | None) -> str:
        if not user_id:
            return "❌ Could not determine your LINE user ID."

        token = (arg or "").strip()
        if not token:
            return "Usage: /admin cancel <token>"

        if not self._is_private_chat(chat_id):
            return "❌ Please cancel in your private chat with the bot."

        ok, msg = admin_confirmation_service.cancel(token, user_id)
        return msg

    async def _get_stats_message(self, line_bot_api: MessagingApi) -> str:
        """
        Generate comprehensive admin statistics dashboard.
        
        Features:
        - System health indicators
        - Usage metrics with trends
        - User engagement analytics
        - Cache performance metrics
        - Session state overview
        """
        snap = metrics_service.snapshot()

        # ====================================================================
        # SECTION 1: LINE API Quota (Critical for service continuity)
        # ====================================================================
        monthly_limit = None
        monthly_used = None
        monthly_left = None
        quota_status_emoji = "✅"
        
        try:
            quota = None
            if hasattr(line_bot_api, "get_message_quota"):
                quota = line_bot_api.get_message_quota()

            consumption = None
            if hasattr(line_bot_api, "get_message_quota_consumption"):
                consumption = line_bot_api.get_message_quota_consumption()

            def _get(obj, key: str):
                if obj is None:
                    return None
                if isinstance(obj, dict):
                    return obj.get(key)
                return getattr(obj, key, None)

            monthly_limit = _get(quota, "value")
            monthly_used = _get(consumption, "totalUsage")
            if isinstance(monthly_limit, int) and isinstance(monthly_used, int):
                monthly_left = max(0, monthly_limit - monthly_used)
                # Set warning emoji if quota is running low
                if monthly_limit > 0:
                    usage_pct = (monthly_used / monthly_limit) * 100
                    if usage_pct >= 90:
                        quota_status_emoji = "🔴"
                    elif usage_pct >= 75:
                        quota_status_emoji = "🟡"
        except Exception as e:
            logger.debug(f"Could not fetch LINE quota: {e}")
            monthly_limit = None

        # ====================================================================
        # SECTION 2: System Metrics
        # ====================================================================
        uptime = metrics_service.get_uptime()
        uptime_hours = int(uptime.total_seconds() // 3600)
        uptime_minutes = int((uptime.total_seconds() % 3600) // 60)
        uptime_days = uptime_hours // 24
        uptime_hours_remaining = uptime_hours % 24

        active_sessions = len(session_manager.get_active_sessions())
        sleeping_chats = len(session_manager.get_sleeping_chats())
        pending_confirms = admin_confirmation_service.count_pending()

        # ====================================================================
        # SECTION 3: News Session Analytics
        # ====================================================================
        news_sessions = 0
        try:
            from src.services.news_session_manager import news_session_manager

            if hasattr(news_session_manager, "_news_sessions"):
                news_session_manager._cleanup_expired_sessions()
                news_sessions = len(news_session_manager._news_sessions)
        except Exception:
            news_sessions = 0

        # ====================================================================
        # SECTION 4: Friend Engagement
        # ====================================================================
        last_friend = "N/A"
        if snap.last_friend_added_at:
            time_ago = datetime.now(timezone.utc) - snap.last_friend_added_at
            if time_ago.total_seconds() < 3600:
                minutes_ago = int(time_ago.total_seconds() // 60)
                time_ago_str = f"{minutes_ago}m ago"
            elif time_ago.total_seconds() < 86400:
                hours_ago = int(time_ago.total_seconds() // 3600)
                time_ago_str = f"{hours_ago}h ago"
            else:
                days_ago = int(time_ago.total_seconds() // 86400)
                time_ago_str = f"{days_ago}d ago"

            last_friend = f"{time_ago_str} ({self._mask_user_id(snap.last_friend_added_user_id)})"

        # ====================================================================
        # SECTION 5: Current Tourism News Headlines
        # ====================================================================
        tourism_headlines = []
        # Reuse news_data_service if available (avoids creating new instance)
        if self._news_data_service:
            try:
                tourism_news = await self._news_data_service.get_news_headlines(language="en")
                tourism_headlines = [item.get("title", "")[:50] + "..." if len(item.get("title", "")) > 50 else item.get("title", "") for item in tourism_news[:3] if item.get("title")]
            except Exception as e:
                logger.debug(f"Could not fetch tourism news for stats: {e}")
                tourism_headlines = []

        # ====================================================================
        # BUILD DASHBOARD MESSAGE
        # ====================================================================
        msg = "📊 **Admin Stats Dashboard**\n" + "═" * 32 + "\n\n"

        # System Status Section
        msg += "🖥️  **SYSTEM STATUS**\n" + "─" * 32 + "\n"
        
        # Uptime with days breakdown
        if uptime_days > 0:
            msg += f"⏱️  Uptime: {uptime_days}d {uptime_hours_remaining}h {uptime_minutes}m\n"
        else:
            msg += f"⏱️  Uptime: {uptime_hours}h {uptime_minutes}m\n"
        
        # LINE quota with visual indicator
        if monthly_left is not None and monthly_limit is not None:
            percentage = (
                (monthly_left / monthly_limit * 100) if monthly_limit > 0 else 0
            )
            msg += f"{quota_status_emoji} LINE quota: {monthly_left:,}/{monthly_limit:,} ({percentage:.1f}% remaining)\n"
        else:
            msg += "ℹ️  LINE quota: Not available\n"
        msg += "\n"

        # Usage Metrics Section (Enhanced)
        msg += "📈 **USAGE METRICS**\n" + "─" * 32 + "\n"
        msg += f"🔤 Translations: {snap.translation_requests_total:,} total\n"
        
        # Provider breakdown with percentages
        total_translations = snap.translation_requests_total
        if total_translations > 0:
            google_pct = (snap.translation_google_total / total_translations) * 100
            libre_pct = (snap.translation_libre_total / total_translations) * 100
            msg += f"   └─ Google: {snap.translation_google_total:,}, Libre: {snap.translation_libre_total:,} ({google_pct:.0f}% / {libre_pct:.0f}%)\n"
        else:
            msg += f"   └─ Google: {snap.translation_google_total:,}, Libre: {snap.translation_libre_total:,}\n"
        
        msg += f"📰 News requests: {snap.news_requests_total:,}\n"
        msg += f"🔧 Admin commands: {snap.admin_commands_total:,}\n"

        # Error metrics (only show if non-zero)
        if snap.failed_translations > 0 or snap.rate_limited_requests > 0:
            msg += f"\n⚠️  **ERROR METRICS**\n"
            if snap.failed_translations > 0:
                msg += f"❌ Failed translations: {snap.failed_translations:,}\n"
            if snap.rate_limited_requests > 0:
                msg += f"⏳ Rate limited: {snap.rate_limited_requests:,}\n"
        msg += "\n"

        # User Engagement Section (Enhanced)
        msg += "👥 **USER ENGAGEMENT**\n" + "─" * 32 + "\n"
        msg += f"👤 Unique users: {snap.unique_users_count:,}\n"
        msg += f"👥 Unique groups: {snap.unique_groups_count:,}\n"
        
        total_unique = snap.unique_users_count + snap.unique_groups_count
        msg += f"📊 Total reach: {total_unique:,} chats\n"
        net_friends = snap.friends_follow_events_total - snap.friends_unfollow_events_total
        msg += (
            f"🤝 Friends (since boot): +{snap.friends_follow_events_total:,} / -{snap.friends_unfollow_events_total:,} / net {net_friends:,}\n"
        )
        msg += f"👋 Last friend added: {last_friend}\n"

        # Peak usage analytics
        if snap.peak_hour is not None:
            msg += f"📈 Peak hour: {snap.peak_hour}:00 UTC ({snap.peak_hour_requests:,} req)\n"
        msg += "\n"

        # Tourism News Section (New)
        if tourism_headlines:
            msg += "🧳 **CURRENT TOURISM NEWS**\n" + "─" * 32 + "\n"
            for i, headline in enumerate(tourism_headlines, 1):
                msg += f"{i}. {headline}\n"
            msg += "\n"

        # Active Sessions Section (Enhanced)
        msg += "💬 **ACTIVE SESSIONS**\n" + "─" * 32 + "\n"
        msg += f"✅ Translation sessions: {active_sessions:,}\n"
        msg += f"📰 News flows: {news_sessions:,}\n"
        msg += f"😴 Sleeping chats: {sleeping_chats:,}\n"
        msg += f"🔐 Pending confirmations: {pending_confirms:,}\n"
        
        # Total active indicator (only show if there are active sessions)
        total_active = active_sessions + news_sessions
        if total_active > 0:
            msg += f"📊 Total active: {total_active:,} sessions\n"

        # Cache Performance Section (Enhanced)
        total_cache_ops = snap.cache_hits_total + snap.cache_misses_total
        if total_cache_ops > 0:
            hit_rate = (
                (snap.cache_hits_total / total_cache_ops * 100)
                if total_cache_ops > 0
                else 0
            )
            
            # Cache quality indicator
            cache_quality_emoji = "🟢" if hit_rate >= 80 else "🟡" if hit_rate >= 60 else "🔴"
            
            msg += "\n"
            msg += "💾 **CACHE PERFORMANCE**\n" + "─" * 32 + "\n"
            msg += f"✅ Hits: {snap.cache_hits_total:,}\n"
            msg += f"❌ Misses: {snap.cache_misses_total:,}\n"
            msg += f"{cache_quality_emoji} Hit rate: {hit_rate:.1f}%\n"

        # Footer with timestamp
        msg += "\n" + "─" * 32 + "\n"
        msg += f"🕐 Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC"

        return msg

    def _purge_chat(self, current_chat_id: str, target_chat_id: str | None = None) -> str:
        """Clear bot internal history/state for a chat (best-effort)."""
        chat_id = target_chat_id or current_chat_id

        # Translation/session state
        had_session = session_manager.end_session(chat_id)
        session_manager.clear_message_history(chat_id)
        was_sleeping = session_manager.wake_chat(chat_id)
        rate_limiter.reset_chat(chat_id)

        # News flow state (import locally to avoid import cycles)
        ended_news = False
        try:
            from src.services.news_session_manager import news_session_manager

            ended_news = news_session_manager.end_news_flow(chat_id)
        except Exception:
            ended_news = False

        # News rate limit (if present)
        try:
            from src.agents.news_agent import news_rate_limiter_friend

            news_rate_limiter_friend.reset_chat(chat_id)
        except Exception:
            pass

        logger.info(f"🔧 Admin purged chat {chat_id}")

        status = "🧹 Purge Complete\n━━━━━━━━━━━━━━━━\n\n"
        status += f"Chat ID: {chat_id}\n\n"
        status += f"{'✅' if had_session else '⏸️'} Session: {'Ended' if had_session else 'Was inactive'}\n"
        status += f"{'☀️' if was_sleeping else '⏸️'} Sleep: {'Woken up' if was_sleeping else 'Was awake'}\n"
        status += "🧹 History: Cleared\n"
        status += f"{'📰' if ended_news else '⏸️'} News flow: {'Ended' if ended_news else 'Was inactive'}\n\n"
        status += "Note: Bots cannot delete/unsend existing LINE chat messages via API."
        return status

    def _parse_leave_target(
        self, current_chat_id: str, arg: str | None
    ) -> tuple[str | None, str | None, str | None]:
        """Parse leave target; returns (kind, raw_id, error). kind is 'group' or 'room'."""
        if not arg or not arg.strip():
            if current_chat_id.startswith("group_"):
                return "group", current_chat_id[len("group_") :], None
            if current_chat_id.startswith("room_"):
                return "room", current_chat_id[len("room_") :], None
            return (
                None,
                None,
                "❌ /admin leave can only be used in a group/room, or with an explicit target.",
            )

        raw = arg.strip()

        # Accept chat_id formats
        if raw.startswith("group_"):
            return "group", raw[len("group_") :], None
        if raw.startswith("room_"):
            return "room", raw[len("room_") :], None

        # Accept explicit kind syntax: "group <id>" / "room <id>"
        parts = raw.split(maxsplit=1)
        if len(parts) == 2 and parts[0].lower() in ("group", "room"):
            kind = parts[0].lower()
            target_id = parts[1].strip()
            if not target_id:
                return None, None, f"❌ Usage: /admin leave {kind} <{kind}_id>"
            return kind, target_id, None

        # Heuristic: LINE group IDs often start with 'C', rooms often start with 'R'
        if raw.startswith("C"):
            return "group", raw, None
        if raw.startswith("R"):
            return "room", raw, None

        return (
            None,
            None,
            "❌ Invalid target. Use /admin leave group <id>, /admin leave room <id>, or group_<id>/room_<id>.",
        )

    async def _leave_chat(
        self,
        event: MessageEvent,
        line_bot_api: MessagingApi,
        current_chat_id: str,
        arg: str | None,
    ) -> None:
        """Leave the specified group/room (or current group/room) and reply with status."""
        kind, target_id, error = self._parse_leave_target(current_chat_id, arg)
        if error or not kind or not target_id:
            message = error or "❌ Could not determine leave target."
            if event.reply_token:
                await asyncio.to_thread(
                    line_bot_api.reply_message,
                    ReplyMessageRequest(
                        replyToken=event.reply_token,
                        messages=[
                            TextMessage(text=message, quickReply=None, quoteToken=None)
                        ],
                        notificationDisabled=False,
                    ),
                )
            return

        # Reply first so the admin sees confirmation even if leaving succeeds immediately.
        leaving_msg = f"🚪 Leaving {kind} {target_id}..."
        if event.reply_token:
            await asyncio.to_thread(
                line_bot_api.reply_message,
                ReplyMessageRequest(
                    replyToken=event.reply_token,
                    messages=[
                        TextMessage(text=leaving_msg, quickReply=None, quoteToken=None)
                    ],
                    notificationDisabled=False,
                ),
            )

        try:
            if kind == "group":
                await asyncio.to_thread(line_bot_api.leave_group, target_id)
            else:
                await asyncio.to_thread(line_bot_api.leave_room, target_id)
            logger.info(f"🚪 Left {kind} {target_id} by admin request")
        except Exception as e:
            logger.error(f"❌ Failed to leave {kind} {target_id}: {e}", exc_info=True)

    def _get_status_message(
        self, current_chat_id: str, target_chat_id: str | None = None
    ) -> str:
        """Get status information for a chat."""
        chat_id = target_chat_id or current_chat_id

        # Check session status
        is_active = session_manager.is_session_active(chat_id)
        is_sleeping = session_manager.is_sleeping(chat_id)
        sleep_remaining = session_manager.get_sleep_remaining(chat_id)
        session_info = session_manager.get_session_info(chat_id)

        # Build status message
        status = "📊 Chat Status\n━━━━━━━━━━━━━━━━\n\n"
        status += f"Chat ID: {chat_id}\n\n"

        if is_sleeping:
            status += f"😴 Status: SLEEPING\n"
            status += f"⏰ Wake in: {sleep_remaining} hour(s)\n"
        elif is_active:
            status += f"✅ Status: ACTIVE\n"
            if session_info:
                status += f"👤 User: {session_info.get('user_id', 'unknown')}\n"
                status += f"📝 Messages: {session_info.get('message_count', 0)}\n"
                started = session_info.get("started_at")
                if started:
                    status += f"🕐 Started: {started.strftime('%Y-%m-%d %H:%M:%S')}\n"
        else:
            status += f"⏸️  Status: INACTIVE\n"

        return status

    def _wake_chat(self, current_chat_id: str, target_chat_id: str | None = None) -> str:
        """Wake a sleeping chat."""
        chat_id = target_chat_id or current_chat_id

        if not session_manager.is_sleeping(chat_id):
            return f"ℹ️  Chat {chat_id} is not sleeping."

        session_manager.wake_chat(chat_id)
        logger.info(f"🔧 Admin force-woke chat {chat_id}")
        return f"☀️ Chat {chat_id} has been woken up!\n\nThe bot is now ready to translate."

    def _sleep_chat(self, current_chat_id: str, arg: str | None = None) -> str:
        """Put a chat to sleep."""
        # Parse arguments: could be "chat_id hours" or just "hours" or just "chat_id"
        if not arg:
            chat_id = current_chat_id
            hours = 24
        else:
            parts = arg.split(maxsplit=1)

            # Check if first part looks like a chat_id or hours
            first_part = parts[0]
            if first_part.startswith(("user_", "group_", "room_")):
                # It's a chat_id
                chat_id = first_part
                hours = int(parts[1]) if len(parts) > 1 else 24
            else:
                # It's hours
                chat_id = current_chat_id
                try:
                    hours = int(first_part)
                except ValueError:
                    return f"❌ Invalid hours: {first_part}\n\nUse: /admin sleep [chat_id] [hours]"

        # Validate hours
        if hours < 1 or hours > 168:  # Max 1 week
            return (
                f"❌ Invalid hours: {hours}\n\nHours must be between 1 and 168 (1 week)."
            )

        session_manager.sleep_chat(chat_id, hours)
        logger.info(f"🔧 Admin put chat {chat_id} to sleep for {hours} hours")
        return f"😴 Chat {chat_id} is now sleeping for {hours} hour(s).\n\nUse '/admin wake' to wake early."

    def _reset_chat(self, current_chat_id: str, target_chat_id: str | None = None) -> str:
        """Reset chat session and history."""
        chat_id = target_chat_id or current_chat_id

        # End session
        had_session = session_manager.end_session(chat_id)

        # Clear message history
        session_manager.clear_message_history(chat_id)

        # Wake if sleeping
        was_sleeping = session_manager.wake_chat(chat_id)

        logger.info(f"🔧 Admin reset chat {chat_id}")

        status = "🔄 Chat Reset Complete\n━━━━━━━━━━━━━━━━\n\n"
        status += f"Chat ID: {chat_id}\n\n"
        status += f"{'✅' if had_session else '⏸️'} Session: {'Ended' if had_session else 'Was inactive'}\n"
        status += f"{'☀️' if was_sleeping else '⏸️'} Sleep: {'Woken up' if was_sleeping else 'Was awake'}\n"
        status += f"🧹 History: Cleared\n\n"
        status += "The chat is now in fresh state!"

        return status

    def _list_sessions(self) -> str:
        """List all active sessions."""
        sessions = session_manager.get_active_sessions()
        sleeping = session_manager.get_sleeping_chats()

        if not sessions and not sleeping:
            return "ℹ️  No active sessions or sleeping chats."

        msg = "📊 Active Sessions\n━━━━━━━━━━━━━━━━\n\n"

        if sessions:
            msg += "✅ ACTIVE SESSIONS:\n"
            for chat_id, info in sessions.items():
                msg += f"\n• {chat_id}\n"
                msg += f"  👤 User: {info.get('user_id', 'unknown')}\n"
                msg += f"  📝 Messages: {info.get('message_count', 0)}\n"

        if sleeping:
            msg += "\n😴 SLEEPING CHATS:\n"
            for chat_id in sleeping:
                remaining = session_manager.get_sleep_remaining(chat_id)
                msg += f"\n• {chat_id}\n"
                msg += f"  ⏰ Wake in: {remaining}h\n"

        return msg

    def _get_chat_id(self, event: MessageEvent) -> str:
        """Extract chat ID from event."""
        if event.source and hasattr(event.source, "group_id"):
            group_id = getattr(event.source, "group_id", None)
            if group_id:
                return f"group_{group_id}"
        if event.source and hasattr(event.source, "room_id"):
            room_id = getattr(event.source, "room_id", None)
            if room_id:
                return f"room_{room_id}"
        if event.source:
            user_id = getattr(event.source, "user_id", "unknown")
            return f"user_{user_id}"
        return "user_unknown"
