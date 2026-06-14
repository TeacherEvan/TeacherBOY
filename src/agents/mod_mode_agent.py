"""Moderator Mode Agent — Priority 4: Intercepts messages in mod-enabled groups."""

import logging
import re

from linebot.v3.messaging import MessagingApi
from linebot.v3.webhooks import MessageEvent, TextMessageContent

from src.agents.base_agent import BaseAgent
from src.agents.mod_mode.dashboard import ModDashboardBuilder
from src.services.ban_list_service import BanListService
from src.services.harmful_content_detector import HarmfulContentDetector
from src.services.mod_audit_log import ModAuditLog
from src.services.mod_mode_service import ModModeService
from src.services.warning_service import WarningService

logger = logging.getLogger(__name__)


class ModModeAgent(BaseAgent):
    """High-priority agent for Moderator Mode message interception."""

    def __init__(
        self,
        mod_mode_service: ModModeService | None,
        ban_list_service: BanListService | None,
        warning_service: WarningService | None,
        harmful_detector: HarmfulContentDetector | None,
        audit_log: ModAuditLog | None,
        dashboard_builder: ModDashboardBuilder,
    ):
        super().__init__(
            name="ModModeAgent",
            description="Moderator Mode: group moderation (kick, warn, ban, dashboard)",
        )
        self._mod_mode = mod_mode_service
        self._ban_list = ban_list_service
        self._warnings = warning_service
        self._detector = harmful_detector
        self._audit = audit_log
        self._dashboard = dashboard_builder

    def get_priority(self) -> int:
        return 4  # Higher than AdminAgent (5)

    async def should_handle(self, event: MessageEvent, text: str) -> bool:
        """Intercept if group has active mod mode or for activation command."""
        logger.debug(f"🔍 ModModeAgent.should_handle: text='{text[:50]}', source_type={getattr(event.source, 'type', None)}")
        if not isinstance(event.message, TextMessageContent):
            logger.debug("🔍 ModModeAgent: Not TextMessageContent, returning False")
            return False

        source = event.source
        if not source or source.type not in ("group", "room"):
            logger.debug(f"🔍 ModModeAgent: Not group/room (type={source.type if source else None}), returning False")
            return False  # Mod mode only in groups/rooms

        group_id = source.group_id if source.type == "group" else source.room_id
        user_id = getattr(source, "user_id", None)
        if not user_id or not group_id:
            logger.debug(f"🔍 ModModeAgent: Missing user_id={user_id} or group_id={group_id}, returning False")
            return False

        # Check activation command (from admin) - allow even if mod mode not active
        if self._is_activation_command(text):
            is_admin = await self._is_admin(user_id)
            logger.info(f"🔍 ModModeAgent: Activation command detected from user={user_id}, is_admin={is_admin}")
            return is_admin

        # Check mod commands that can activate mod mode (allow even if mod mode not active)
        if self._is_activation_mod_command(text):
            is_admin = await self._is_admin(user_id)
            logger.info(f"🔍 ModModeAgent: /modmode activation command from user={user_id}, is_admin={is_admin}")
            return is_admin

        # If mod mode service is not available, we cannot check mod mode active or handle non-mod commands
        if self._mod_mode is None:
            logger.warning("🔍 ModModeAgent: mod_mode service is None, cannot check mod mode, returning False")
            return False

        # Check if mod mode is active in this group
        is_active = await self._mod_mode.is_mod_mode_active(group_id)
        logger.debug(f"🔍 ModModeAgent: group={group_id} mod_mode_active={is_active}")
        if not is_active:
            # Check if this is a /modmode command that activates mod mode (all/special)
            # These should be handled even when mod mode is not active
            if text.strip().lower().startswith("/modmode"):
                subcmd = self._parse_modmode_subcommand(text)
                logger.debug(f"🔍 ModModeAgent: mod mode not active, subcmd={subcmd}")
                if subcmd in ("all", "special"):
                    is_admin = await self._is_admin(user_id)
                    logger.info(f"🔍 ModModeAgent: /modmode {subcmd} (activates mod mode) from user={user_id}, is_admin={is_admin}")
                    return is_admin
            return False

        # Check other mod commands (require admin)
        if self._is_mod_command(text):
            is_admin = await self._is_admin(user_id)
            logger.info(f"🔍 ModModeAgent: Mod command from user={user_id}, is_admin={is_admin}")
            return is_admin

        # Intercept message in mod-enabled group for processing
        logger.debug(f"🔍 ModModeAgent: Intercepting message in mod-enabled group={group_id}")
        return True

    async def handle(self, event: MessageEvent, text: str, line_bot_api: MessagingApi) -> bool:
        """Process mod mode message."""
        source = event.source
        group_id = source.group_id if source.type == "group" else source.room_id
        user_id = getattr(source, "user_id", None)

        logger.info(f"🔧 ModModeAgent.handle: user={user_id}, group={group_id}, text='{text[:50]}'")

        try:
            # 1. Activation command
            if self._is_activation_command(text):
                logger.info(f"🔧 ModModeAgent: Handling activation command for user={user_id}")
                return await self._handle_activation(event, line_bot_api)

            # 2. Mod commands (/modmode ...)
            if self._is_mod_command(text):
                logger.info(f"🔧 ModModeAgent: Handling /modmode command for user={user_id}")
                return await self._handle_mod_command(event, line_bot_api, text)

            # 3. Banned user -> kick
            if self._ban_list and await self._ban_list.is_banned(group_id, user_id):
                logger.warning(f"🔧 ModModeAgent: Banned user {user_id} in group {group_id}, kicking")
                return await self._kick_user(group_id, user_id, line_bot_api, "banned")

            # 4. Special mode: block non-allowed users
            if self._mod_mode and not await self._mod_mode.is_user_allowed(group_id, user_id):
                logger.warning(f"🔧 ModModeAgent: User {user_id} not allowed in special mode group {group_id}")
                return await self._warn_user(group_id, user_id, line_bot_api, "Not allowed to speak in special mode")

            # 5. Harmful content detection in "all" mode
            if self._mod_mode and await self._should_detect_harmful(group_id, text):
                logger.info(f"🔧 ModModeAgent: Checking harmful content for user={user_id}")
                detection = await self._detector.detect(text)
                if detection["is_harmful"]:
                    logger.warning(f"🔧 ModModeAgent: Harmful content detected for user={user_id}: {detection['matched_keywords']}")
                    return await self._handle_harmful_content(event, line_bot_api, detection)

            logger.debug("🔧 ModModeAgent: No action needed, letting other agents handle")
            return False  # Let other agents handle

        except Exception as e:
            logger.error(f"❌ ModModeAgent error: {e}", exc_info=True)
            return False

    # ===== Activation =====

    def _is_activation_command(self, text: str) -> bool:
        return re.search(r"activate\s+mod\s+mode", text, re.IGNORECASE) is not None

    def _is_activation_mod_command(self, text: str) -> bool:
        """Check if text is a /modmode command that activates mod mode (all/special)."""
        import re
        text_lower = text.strip().lower()
        if not text_lower.startswith("/modmode"):
            return False
        # Use regex with word boundary to match subcommand, allowing trailing punctuation
        match = re.search(r"/modmode\s+(all|special)\b", text_lower)
        return match is not None

    async def _handle_activation(self, event: MessageEvent, line_bot_api: MessagingApi) -> bool:
        source = event.source
        group_id = source.group_id if source.type == "group" else source.room_id
        user_id = source.user_id

        # Determine mode from text
        text_lower = event.message.text.lower()
        mode = "all"
        special_user_id = None

        if "special" in text_lower:
            mode = "special"
            # Extract @mention from LINE message mention entity
            special_user_id = None
            if hasattr(event.message, "mention") and event.message.mention:
                mentionees = getattr(event.message.mention, "mentionees", [])
                if mentionees:
                    # Use the first mentioned user
                    special_user_id = mentionees[0].user_id
            if not special_user_id:
                # Fallback: try regex from text (for backwards compatibility)
                mention_match = re.search(r"@(\w+)", event.message.text)
                if mention_match:
                    special_user_id = mention_match.group(1)
            if not special_user_id:
                await self._reply(event, "❌ Usage: 'activate mod mode special @user'", line_bot_api)
                return True

        await self._mod_mode.activate_mod_mode(group_id, user_id, mode, special_user_id)
        await self._audit.log_mode_change(group_id, user_id, mode, True, special_user_id)

        mode_msg = (
            "ALL USERS (normal chat, harmful content monitored)" if mode == "all" else f"SPECIAL MODE (only you + @{special_user_id} can speak)"
        )
        await self._reply(
            f"🛡️ Moderator Mode ACTIVATED\nMode: {mode_msg}\nUse /modmode for dashboard",
            line_bot_api,
        )
        return True

    # ===== Mod Commands =====

    def _is_mod_command(self, text: str) -> bool:
        return text.strip().lower().startswith("/modmode")

    def _parse_modmode_subcommand(self, text: str) -> str | None:
        """Extract subcommand from /modmode command, ignoring trailing punctuation."""
        import re
        text_lower = text.strip().lower()
        match = re.search(r"/modmode\s+(\w+)", text_lower)
        return match.group(1) if match else None

    def _parse_modmode_args(self, text: str) -> list[str]:
        """Parse full arguments for /modmode command, preserving @mentions."""
        # Split but preserve @mentions
        parts = text.strip().split()
        return parts[2:] if len(parts) >= 3 else []

    async def _handle_mod_command(self, event: MessageEvent, line_bot_api: MessagingApi, text: str) -> bool:
        source = event.source
        group_id = source.group_id if source.type == "group" else source.room_id
        user_id = source.user_id

        subcmd = self._parse_modmode_subcommand(text)
        if not subcmd:
            return await self._show_dashboard(event, line_bot_api)

        args = self._parse_modmode_args(text)

        if subcmd == "all":
            await self._mod_mode.activate_mod_mode(group_id, user_id, "all")
            await self._audit.log_mode_change(group_id, user_id, "all", True)
            await self._reply("✅ Mod mode: ALL USERS (normal chat, harmful content monitored)", line_bot_api)
            return True

        if subcmd == "special":
            if not args:
                await self._reply("Usage: /modmode special @user", line_bot_api)
                return True
            special_id = args[0].lstrip("@")
            await self._mod_mode.set_special_user(group_id, special_id)
            await self._audit.log_mode_change(group_id, user_id, "special", True, special_id)
            await self._reply(f"✅ Mod mode: SPECIAL (only admin + @{special_id} can speak)", line_bot_api)
            return True

        if subcmd == "off":
            await self._mod_mode.deactivate_mod_mode(group_id)
            await self._audit.log_mode_change(group_id, user_id, "all", False)
            await self._reply("🛑 Moderator Mode DEACTIVATED", line_bot_api)
            return True

        if subcmd == "dashboard":
            return await self._show_dashboard(event, line_bot_api)

        if subcmd == "kick":
            return await self._handle_kick_command(event, line_bot_api, ["/modmode", "kick"] + args)

        if subcmd == "warn":
            return await self._handle_warn_command(event, line_bot_api, ["/modmode", "warn"] + args)

        if subcmd == "ban":
            return await self._handle_ban_command(event, line_bot_api, ["/modmode", "ban"] + args)

        if subcmd == "banlist":
            return await self._show_ban_list(event, line_bot_api)

        if subcmd == "warnlist":
            return await self._show_warn_list(event, line_bot_api)

        if subcmd == "unban":
            return await self._handle_unban_command(event, line_bot_api, ["/modmode", "unban"] + args)

        await self._reply("❌ Unknown /modmode command. Use /modmode dashboard", line_bot_api)
        return True

    # ===== Kick/Warn/Ban =====

    async def _kick_user(self, group_id: str, user_id: str, line_bot_api: MessagingApi, reason: str) -> bool:
        """Kick user via LINE API."""
        # Protect special user from being kicked
        if self._mod_mode:
            info = await self._mod_mode.get_mod_mode_info(group_id)
            if info and info.get("mode") == "special":
                special_user_id = info.get("special_user_id")
                if special_user_id and user_id == special_user_id:
                    logger.warning(f"⚠️ Attempted to kick special user {user_id} - blocked")
                    return False
        try:
            # LINE Bot SDK v3: kick from group
            if hasattr(line_bot_api, "kick_users"):
                line_bot_api.kick_users(group_id, [user_id])
            await self._audit.log_kick(group_id, user_id, "system", reason)
            logger.info(f"👢 Kicked banned user {user_id} from {group_id} (reason: {reason})")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to kick {user_id}: {e}")
            return False

    async def _warn_user(self, group_id: str, user_id: str, line_bot_api: MessagingApi, reason: str) -> bool:
        result = await self._warnings.warn_user(group_id, user_id, "system", reason)
        count = result["count"]
        await self._audit.log_warn(group_id, user_id, "system", reason, count)

        if result["should_ban"]:
            await self._audit.log_ban(group_id, user_id, "system", f"Auto-ban after {count} warnings")
            await self._kick_user(group_id, user_id, line_bot_api, f"Auto-ban ({count} warnings)")
            await self._reply(f"🔨 @{user_id} BANNED after {count} warnings", line_bot_api)
        else:
            await self._reply(f"⚠️ @{user_id} Warning {count}/3: {reason}", line_bot_api)

        return True

    async def _handle_kick_command(self, event, line_bot_api, parts):
        """Handle /modmode kick @user_id command."""
        source = event.source
        group_id = source.group_id if source.type == "group" else source.room_id
        admin_id = source.user_id

        if len(parts) < 3:
            await self._reply("Usage: /modmode kick @user_id", line_bot_api)
            return True

        target_user_id = parts[2].lstrip("@")
        if not target_user_id:
            await self._reply("❌ Invalid user ID", line_bot_api)
            return True

        if not await self._is_admin(admin_id):
            await self._reply("❌ Admin only", line_bot_api)
            return True

        # Check if target is special user (protected)
        if self._mod_mode:
            info = await self._mod_mode.get_mod_mode_info(group_id)
            if info and info.get("mode") == "special":
                special_user_id = info.get("special_user_id")
                if special_user_id and target_user_id == special_user_id:
                    await self._reply(f"❌ Cannot kick @{target_user_id} - protected as special user in SPECIAL mode", line_bot_api)
                    return True

        # Kick the user
        success = await self._kick_user(group_id, target_user_id, line_bot_api, "Kicked via /modmode kick")
        await self._audit.log_kick(group_id, target_user_id, admin_id, "Kicked via /modmode kick")
        if success:
            await self._reply(f"👢 Kicked @{target_user_id}", line_bot_api)
        else:
            await self._reply(f"❌ Failed to kick @{target_user_id}", line_bot_api)
        return True

    async def _handle_warn_command(self, event, line_bot_api, parts):
        """Handle /modmode warn @user_id [reason] command."""
        source = event.source
        group_id = source.group_id if source.type == "group" else source.room_id
        admin_id = source.user_id

        if len(parts) < 3:
            await self._reply("Usage: /modmode warn @user_id [reason]", line_bot_api)
            return True

        target_user_id = parts[2].lstrip("@")
        if not target_user_id:
            await self._reply("❌ Invalid user ID", line_bot_api)
            return True

        reason = " ".join(parts[3:]) if len(parts) > 3 else "No reason provided"

        if not await self._is_admin(admin_id):
            await self._reply("❌ Admin only", line_bot_api)
            return True

        # Use existing _warn_user which handles 3-strike auto-ban
        # Pass admin_id as warned_by for audit trail
        result = await self._warnings.warn_user(group_id, target_user_id, admin_id, reason)
        count = result["count"]
        await self._audit.log_warn(group_id, target_user_id, admin_id, reason, count)

        if result["should_ban"]:
            await self._audit.log_ban(group_id, target_user_id, admin_id, f"Auto-ban after {count} warnings")
            await self._kick_user(group_id, target_user_id, line_bot_api, f"Auto-ban ({count} warnings)")
            await self._reply(f"🔨 @{target_user_id} BANNED after {count} warnings", line_bot_api)
        else:
            await self._reply(f"⚠️ @{target_user_id} Warning {count}/3: {reason}", line_bot_api)

        return True

    async def _handle_ban_command(self, event, line_bot_api, parts):
        """Handle /modmode ban @user_id [reason] command - ban + immediate kick."""
        source = event.source
        group_id = source.group_id if source.type == "group" else source.room_id
        admin_id = source.user_id

        if len(parts) < 3:
            await self._reply("Usage: /modmode ban @user_id [reason]", line_bot_api)
            return True

        target_user_id = parts[2].lstrip("@")
        if not target_user_id:
            await self._reply("❌ Invalid user ID", line_bot_api)
            return True

        reason = " ".join(parts[3:]) if len(parts) > 3 else "Banned by admin"

        if not await self._is_admin(admin_id):
            await self._reply("❌ Admin only", line_bot_api)
            return True

        # Add to ban list
        await self._ban_list.ban_user(group_id, target_user_id, admin_id, reason)
        await self._audit.log_ban(group_id, target_user_id, admin_id, reason)

        # Kick immediately
        await self._kick_user(group_id, target_user_id, line_bot_api, reason)
        await self._audit.log_kick(group_id, target_user_id, admin_id, reason)

        await self._reply(f"🔨 Banned and kicked @{target_user_id}: {reason}", line_bot_api)
        return True

    async def _handle_unban_command(self, event, line_bot_api, parts):
        """Handle /modmode unban @user_id command - remove from ban list."""
        source = event.source
        group_id = source.group_id if source.type == "group" else source.room_id
        admin_id = source.user_id

        if len(parts) < 3:
            await self._reply("Usage: /modmode unban @user_id", line_bot_api)
            return True

        target_user_id = parts[2].lstrip("@")
        if not target_user_id:
            await self._reply("❌ Invalid user ID", line_bot_api)
            return True

        if not await self._is_admin(admin_id):
            await self._reply("❌ Admin only", line_bot_api)
            return True

        success = await self._ban_list.unban_user(group_id, target_user_id)
        if success:
            await self._audit.log_mode_change(group_id, admin_id, "unban", True, target_user_id)
            await self._reply(f"✅ Unbanned @{target_user_id}", line_bot_api)
        else:
            await self._reply(f"❌ Failed to unban @{target_user_id} (not found?)", line_bot_api)
        return True

    # ===== Dashboard =====

    async def _show_dashboard(self, event, line_bot_api):
        source = event.source
        group_id = source.group_id if source.type == "group" else source.room_id
        info = await self._mod_mode.get_mod_mode_info(group_id)
        _flex = self._dashboard.build_main_dashboard("Group", group_id, info or {})
        # Send Flex message
        return True

    async def _show_ban_list(self, event, line_bot_api):
        # ... build and send ban list flex
        return True

    async def _show_warn_list(self, event, line_bot_api):
        # ... build and send warn list flex
        return True

    # ===== Harmful Content =====

    async def _should_detect_harmful(self, group_id: str, text: str) -> bool:
        info = await self._mod_mode.get_mod_mode_info(group_id)
        return info and info.get("mode") == "all"

    async def _handle_harmful_content(self, event, line_bot_api, detection):
        source = event.source
        group_id = source.group_id if source.type == "group" else source.room_id
        user_id = source.user_id
        keywords = ", ".join(detection["matched_keywords"])
        return await self._warn_user(group_id, user_id, line_bot_api, f"Harmful content: {keywords}")

    # ===== Helpers =====

    async def _is_admin(self, user_id: str) -> bool:
        from src.services.privilege_service import privilege_service

        return privilege_service.is_admin(user_id)

    async def _reply(self, text: str, line_bot_api: MessagingApi):
        # Simplified - would use reply_token in real implementation
        pass
