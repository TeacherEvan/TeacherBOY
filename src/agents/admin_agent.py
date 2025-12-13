"""Admin agent - Handles admin control commands for bot management."""

import logging
from linebot.v3.webhooks import MessageEvent
from linebot.v3.messaging import (
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
)

from .base_agent import BaseAgent
from src.services.session_manager import session_manager
from src.services.rate_limiter import rate_limiter
from src.config import settings

logger = logging.getLogger(__name__)


class AdminAgent(BaseAgent):
    """Agent for handling admin control commands."""

    def __init__(self):
        super().__init__(
            name="AdminAgent",
            description="Admin commands for bot management and control",
        )
        self._admin_user_ids = settings.get_admin_user_ids()
        self._admin_setup_key = (
            settings.admin_setup_key.strip() if isinstance(settings.admin_setup_key, str) else None
        )
        self._claimed_admin_user_id: str | None = None
        
        if self._admin_user_ids:
            logger.info(f"✅ AdminAgent initialized with {len(self._admin_user_ids)} authorized admin(s)")
        else:
            logger.warning("⚠️  AdminAgent initialized but no admin users configured (ADMIN_USER_IDS)")

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
        return text_lower.startswith("/admin") or text_lower.startswith("!admin")

    def _parse_admin_command(self, text: str) -> tuple[str | None, str | None]:
        """Parse '/admin <cmd> [args...]' into (cmd, args)."""
        parts = text.strip().split(maxsplit=2)
        if len(parts) < 2:
            return None, None
        cmd = parts[1].lower()
        arg = parts[2] if len(parts) > 2 else None
        return cmd, arg

    async def should_handle(self, event: MessageEvent, text: str) -> bool:
        """Handle if message is an admin command from an authorized user (or bootstrap claim)."""
        if not self._is_admin_command(text):
            return False
        
        # Get user ID from event
        user_id = getattr(event.source, 'user_id', None) if event.source else None
        if not user_id:
            return False

        # Allow bootstrap claim when configured (even if user isn't an admin yet)
        cmd, _ = self._parse_admin_command(text)
        if cmd == "claim" and self._admin_setup_key:
            return True

        return self._is_admin(user_id)

    async def handle(self, event: MessageEvent, text: str, line_bot_api: MessagingApi) -> bool:
        """Process admin command."""
        chat_id = self._get_chat_id(event)
        user_id = getattr(event.source, 'user_id', None) if event.source else None
        
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
                elif command == "status":
                    response = self._get_status_message(chat_id, arg)
                elif command == "wake":
                    response = self._wake_chat(chat_id, arg)
                elif command == "sleep":
                    response = self._sleep_chat(chat_id, arg)
                elif command == "reset":
                    response = self._reset_chat(chat_id, arg)
                elif command == "sessions":
                    response = self._list_sessions()
                else:
                    response = f"❌ Unknown command: {command}\n\nUse /admin help for available commands."
            
            # Send response
            if event.reply_token:
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        replyToken=event.reply_token,
                        messages=[TextMessage(text=response, quickReply=None, quoteToken=None)],
                        notificationDisabled=False
                    )
                )
            
            logger.info(f"🔧 Admin command executed by {user_id} in chat {chat_id}: {text}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Admin agent error: {e}", exc_info=True)
            
            # Send error message
            if event.reply_token:
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        replyToken=event.reply_token,
                        messages=[TextMessage(
                            text=f"❌ Error executing command: {str(e)}\n\nUse /admin help for usage.",
                            quickReply=None,
                            quoteToken=None
                        )],
                        notificationDisabled=False
                    )
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
            logger.warning(f"⚠️  Invalid admin claim attempt from user {user_id} in {chat_id}")
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
            "📊 Status & Info:\n"
            "  /admin status [chat_id]\n"
            "    → Show current chat status\n\n"
            "  /admin sessions\n"
            "    → List all active sessions\n\n"
            "😴 Sleep Management:\n"
            "  /admin sleep [chat_id] [hours]\n"
            "    → Put chat to sleep (default: 24h)\n\n"
            "  /admin wake [chat_id]\n"
            "    → Wake sleeping chat\n\n"
            "🔄 Session Control:\n"
            "  /admin reset [chat_id]\n"
            "    → Reset chat session & history\n\n"
            "💡 Tips:\n"
            "• [chat_id] is optional - defaults to current chat\n"
            "• Chat IDs format: user_U123..., group_C123...\n"
            "• Use 'sessions' to see active chat IDs"
        )

    def _get_status_message(self, current_chat_id: str, target_chat_id: str = None) -> str:
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
                started = session_info.get('started_at')
                if started:
                    status += f"🕐 Started: {started.strftime('%Y-%m-%d %H:%M:%S')}\n"
        else:
            status += f"⏸️  Status: INACTIVE\n"
        
        return status

    def _wake_chat(self, current_chat_id: str, target_chat_id: str = None) -> str:
        """Wake a sleeping chat."""
        chat_id = target_chat_id or current_chat_id
        
        if not session_manager.is_sleeping(chat_id):
            return f"ℹ️  Chat {chat_id} is not sleeping."
        
        session_manager.wake_chat(chat_id)
        logger.info(f"🔧 Admin force-woke chat {chat_id}")
        return f"☀️ Chat {chat_id} has been woken up!\n\nThe bot is now ready to translate."

    def _sleep_chat(self, current_chat_id: str, arg: str = None) -> str:
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
            return f"❌ Invalid hours: {hours}\n\nHours must be between 1 and 168 (1 week)."
        
        session_manager.sleep_chat(chat_id, hours)
        logger.info(f"🔧 Admin put chat {chat_id} to sleep for {hours} hours")
        return f"😴 Chat {chat_id} is now sleeping for {hours} hour(s).\n\nUse '/admin wake' to wake early."

    def _reset_chat(self, current_chat_id: str, target_chat_id: str = None) -> str:
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
