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
        send_flex_reply=None,
    ) -> None:
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
        self._send_flex_reply = send_flex_reply

    def get_priority(self) -> int:
        return 4

    async def should_handle(self, event: MessageEvent, text: str) -> bool:
        """Intercept if group has active mod mode or for activation command."""
        logger.debug(f"🔍 ModModeAgent.should_handle: text='{text[:50]}', source_type={getattr(event.source, 'type', None)}")
        if not isinstance(event.message, TextMessageContent):
            logger.debug("🔍 ModModeAgent: Not TextMessageContent, returning False")
            return False

        source = event.source
        if not source or source.type not in ("group", "room"):
            logger.debug(f"🔍 ModModeAgent: Not group/room (type={source.type if source else None}), returning False")
            return False

        group_id = source.group_id if source.type == "group" else source.room_id
        user_id = getattr(source, "user_id", None)
        if not user_id or not group_id:
            logger.debug(f"🔍 ModModeAgent: Missing user_id={user_id} or group_id={group_id}, returning False")
            return False

        if self._is_activation_command(text):
            is_admin = await self._is_admin(user_id)
            logger.info(f"🔍 ModModeAgent: Activation command detected from user={user_id}, is_admin={is_admin}")
            return is_admin

        if self._is_activation_mod_command(text):
            is_admin = await self._is_admin(user_id)
            logger.info(f"🔍 ModModeAgent: /modmode activation command from user={user_id}, is_admin={is_admin}")
            return is_admin

        if self._mod_mode is None:
            if text.strip().lower().startswith("/modmode"):
                is_admin = await self._is_admin(user_id)
                logger.info(f"🔍 ModModeAgent: /modmode command detected (services None), is_admin={is_admin}")
                return is_admin
            logger.warning("🔍 ModModeAgent: mod_mode service is None, cannot check mod mode, returning False")
            return False

        is_active = await self._mod_mode.is_mod_mode_active(group_id)
        logger.debug(f"🔍 ModModeAgent: group={group_id} mod_mode_active={is_active}")
        if not is_active:
            if text.strip().lower().startswith("/modmode"):
                subcmd = self._parse_modmode_subcommand(text)
                logger.debug(f"🔍 ModModeAgent: mod mode not active, subcmd={subcmd}")
                if subcmd in ("all", "special"):
                    is_admin = await self._is_admin(user_id)
                    logger.info(
                        f"🔍 ModModeAgent: /modmode {subcmd} (activates mod mode) from user={user_id}, is_admin={is_admin}"
                    )
                    return is_admin
            return False

        if self._is_mod_command(text):
            is_admin = await self._is_admin(user_id)
            logger.info(f"🔍 ModModeAgent: Mod command from user={user_id}, is_admin={is_admin}")
            return is_admin

        logger.debug(f"🔍 ModModeAgent: Intercepting message in mod-enabled group={group_id}")
        return True

    async def handle(self, event: MessageEvent, text: str, line_bot_api: MessagingApi) -> bool:
        """Process mod mode message."""
        source = event.source
        group_id = source.group_id if source.type == "group" else source.room_id
        user_id = getattr(source, "user_id", None)

        logger.info(f"🔧 ModModeAgent.handle: user={user_id}, group={group_id}, text='{text[:50]}'")

        if self._mod_mode is None or self._ban_list is None or self._warnings is None:
            await self._reply(
                event,
                "❌ Moderator Mode services are currently unavailable. Please verify that Convex is configured correctly.",
                line_bot_api,
            )
            return True

        try:
            if self._is_activation_command(text):
                logger.info(f"🔧 ModModeAgent: Handling activation command for user={user_id}")
                return await self._handle_activation(event, line_bot_api)

            if self._is_mod_command(text):
                logger.info(f"🔧 ModModeAgent: Handling /modmode command for user={user_id}")
                return await self._handle_mod_command(event, line_bot_api, text)

            if self._ban_list and await self._ban_list.is_banned(group_id, user_id):
                logger.warning(f"🔧 ModModeAgent: Banned user {user_id} in group {group_id}, kicking")
                return await self._kick_user(group_id, user_id, line_bot_api, "banned")

            if self._mod_mode and not await self._mod_mode.is_user_allowed(group_id, user_id):
                logger.warning(f"🔧 ModModeAgent: User {user_id} not allowed in special mode group {group_id}")
                return await self._warn_user(event, group_id, user_id, line_bot_api, "Not allowed to speak in special mode")

            if self._mod_mode and await self._should_detect_harmful(group_id, text):
                logger.info(f"🔧 ModModeAgent: Checking harmful content for user={user_id}")
                detection = await self._detector.detect(text)
                if detection["is_harmful"]:
                    logger.warning(
                        f"🔧 ModModeAgent: Harmful content detected for user={user_id}: {detection['matched_keywords']}"
                    )
                    return await self._handle_harmful_content(event, line_bot_api, detection)

            logger.debug("🔧 ModModeAgent: No action needed, letting other agents handle")
            return False
        except Exception as e:
            logger.error(f"❌ ModModeAgent error: {e}", exc_info=True)
            return False

    # ===== Activation =====

    def _is_activation_command(self, text: str) -> bool:
        return re.search(r"activate\s+mod\s+mode", text, re.IGNORECASE) is not None

    def _is_activation_mod_command(self, text: str) -> bool:
        text_lower = text.strip().lower()
        if not text_lower.startswith("/modmode"):
            return False
        return re.search(r"/modmode\s+(all|special)\b", text_lower) is not None

    async def _handle_activation(self, event: MessageEvent, line_bot_api: MessagingApi) -> bool:
        source = event.source
        group_id = source.group_id if source.type == "group" else source.room_id
        user_id = source.user_id

        text_lower = event.message.text.lower()
        mode = "all"
        special_user_id = None

        if "special" in text_lower:
            mode = "special"
            special_user_id = None
            if hasattr(event.message, "mention") and event.message.mention:
                mentionees = getattr(event.message.mention, "mentionees", [])
                if mentionees:
                    special_user_id = mentionees[0].user_id
            if not special_user_id:
                mention_match = re.search(r"@(\w+)", event.message.text)
                if mention_match:
                    special_user_id = mention_match.group(1)
            if not special_user_id:
                await self._reply(event, "❌ Usage: 'activate mod mode special @user'", line_bot_api)
                return True

        await self._mod_mode.activate_mod_mode(group_id, user_id, mode, special_user_id)
        if self._audit:
            await self._audit.log_mode_change(group_id, user_id, mode, True, special_user_id)

        mode_msg = (
            "ALL USERS (normal chat, harmful content monitored)"
            if mode == "all"
            else f"SPECIAL MODE (only you + @{special_user_id} can speak)"
        )
        await self._reply(
            event,
            f"🛡️ Moderator Mode ACTIVATED\nMode: {mode_msg}\nUse /modmode for dashboard",
            line_bot_api,
        )
        return True

    # ===== Mod Commands =====

    def _is_mod_command(self, text: str) -> bool:
        return text.strip().lower().startswith("/modmode")

    def _parse_modmode_subcommand(self, text: str) -> str | None:
        text_lower = text.strip().lower()
        match = re.search(r"/modmode\s+(\w+)", text_lower)
        return match.group(1) if match else None

    def _parse_modmode_args(self, text: str) -> list[str]:
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
            if self._audit:
                await self._audit.log_mode_change(group_id, user_id, "all", True)
            await self._reply(event, "✅ Mod mode: ALL USERS (normal chat, harmful content monitored)", line_bot_api)
            return True

        if subcmd == "special":
            special_id = None
            if hasattr(event.message, "mention") and event.message.mention:
                mentionees = getattr(event.message.mention, "mentionees", [])
                if mentionees:
                    special_id = mentionees[0].user_id
            if not special_id and args:
                special_id = args[0].lstrip("@")

            if not special_id:
                await self._reply(event, "Usage: /modmode special @user", line_bot_api)
                return True

            await self._mod_mode.set_special_user(group_id, special_id)
            if self._audit:
                await self._audit.log_mode_change(group_id, user_id, "special", True, special_id)
            await self._reply(event, f"✅ Mod mode: SPECIAL (only admin + @{special_id} can speak)", line_bot_api)
            return True

        if subcmd == "off":
            await self._mod_mode.deactivate_mod_mode(group_id)
            if self._audit:
                await self._audit.log_mode_change(group_id, user_id, "all", False)
            await self._reply(event, "🛑 Moderator Mode DEACTIVATED", line_bot_api)
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

        await self._reply(event, "❌ Unknown /modmode command. Use /modmode dashboard", line_bot_api)
        return True

    # ===== Kick/Warn/Ban =====

    async def _kick_user(self, group_id: str, user_id: str, line_bot_api: MessagingApi, reason: str) -> bool:
        if self._mod_mode:
            info = await self._mod_mode.get_mod_mode_info(group_id)
            if info and info.get("mode") == "special":
                special_user_id = info.get("special_user_id")
                if special_user_id and user_id == special_user_id:
                    logger.warning(f"⚠️ Attempted to kick special user {user_id} - blocked")
                    return False
        try:
            if hasattr(line_bot_api, "kick_users"):
                line_bot_api.kick_users(group_id, [user_id])
            if self._audit:
                await self._audit.log_kick(group_id, user_id, "system", reason)
            logger.info(f"👢 Kicked banned user {user_id} from {group_id} (reason: {reason})")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to kick {user_id}: {e}")
            return False

    async def _warn_user(self, event, group_id: str, user_id: str, line_bot_api: MessagingApi, reason: str) -> bool:
        result = await self._warnings.warn_user(group_id, user_id, "system", reason)
        count = result["count"]
        if self._audit:
            await self._audit.log_warn(group_id, user_id, "system", reason, count)

        if result["should_ban"]:
            if self._audit:
                await self._audit.log_ban(group_id, user_id, "system", f"Auto-ban after {count} warnings")
            await self._kick_user(group_id, user_id, line_bot_api, f"Auto-ban ({count} warnings)")
            await self._reply(event, f"🔨 @{user_id} BANNED after {count} warnings", line_bot_api)
        else:
            await self._reply(event, f"⚠️ @{user_id} Warning {count}/3: {reason}", line_bot_api)

        return True

    async def _handle_kick_command(self, event, line_bot_api, parts):
        source = event.source
        group_id = source.group_id if source.type == "group" else source.room_id
        admin_id = source.user_id

        if len(parts) < 3:
            await self._reply(event, "Usage: /modmode kick @user_id", line_bot_api)
            return True

        target_user_id = self._get_target_user_id(event, parts)
        if not target_user_id:
            await self._reply(event, "❌ Invalid user ID", line_bot_api)
            return True

        if not await self._is_admin(admin_id):
            await self._reply(event, "❌ Admin only", line_bot_api)
            return True

        if self._mod_mode:
            info = await self._mod_mode.get_mod_mode_info(group_id)
            if info and info.get("mode") == "special":
                special_user_id = info.get("special_user_id")
                if special_user_id and target_user_id == special_user_id:
                    await self._reply(
                        event,
                        f"❌ Cannot kick @{target_user_id} - protected as special user in SPECIAL mode",
                        line_bot_api,
                    )
                    return True

        success = await self._kick_user(group_id, target_user_id, line_bot_api, "Kicked via /modmode kick")
        if self._audit:
            await self._audit.log_kick(group_id, target_user_id, admin_id, "Kicked via /modmode kick")
        if success:
            await self._reply(event, f"👢 Kicked @{target_user_id}", line_bot_api)
        else:
            await self._reply(event, f"❌ Failed to kick @{target_user_id}", line_bot_api)
        return True

    async def _handle_warn_command(self, event, line_bot_api, parts):
        source = event.source
        group_id = source.group_id if source.type == "group" else source.room_id
        admin_id = source.user_id

        if len(parts) < 3:
            await self._reply(event, "Usage: /modmode warn @user_id [reason]", line_bot_api)
            return True

        target_user_id = self._get_target_user_id(event, parts)
        if not target_user_id:
            await self._reply(event, "❌ Invalid user ID", line_bot_api)
            return True

        reason = " ".join(parts[3:]) if len(parts) > 3 else "No reason provided"

        if not await self._is_admin(admin_id):
            await self._reply(event, "❌ Admin only", line_bot_api)
            return True

        result = await self._warnings.warn_user(group_id, target_user_id, admin_id, reason)
        count = result["count"]
        if self._audit:
            await self._audit.log_warn(group_id, target_user_id, admin_id, reason, count)

        if result["should_ban"]:
            if self._audit:
                await self._audit.log_ban(group_id, target_user_id, admin_id, f"Auto-ban after {count} warnings")
            await self._kick_user(group_id, target_user_id, line_bot_api, f"Auto-ban ({count} warnings)")
            await self._reply(event, f"🔨 @{target_user_id} BANNED after {count} warnings", line_bot_api)
        else:
            await self._reply(event, f"⚠️ @{target_user_id} Warning {count}/3: {reason}", line_bot_api)

        return True

    async def _handle_ban_command(self, event, line_bot_api, parts):
        source = event.source
        group_id = source.group_id if source.type == "group" else source.room_id
        admin_id = source.user_id

        if len(parts) < 3:
            await self._reply(event, "Usage: /modmode ban @user_id [reason]", line_bot_api)
            return True

        target_user_id = self._get_target_user_id(event, parts)
        if not target_user_id:
            await self._reply(event, "❌ Invalid user ID", line_bot_api)
            return True

        reason = " ".join(parts[3:]) if len(parts) > 3 else "Banned by admin"

        if not await self._is_admin(admin_id):
            await self._reply(event, "❌ Admin only", line_bot_api)
            return True

        await self._ban_list.ban_user(group_id, target_user_id, admin_id, reason)
        if self._audit:
            await self._audit.log_ban(group_id, target_user_id, admin_id, reason)
        await self._kick_user(group_id, target_user_id, line_bot_api, reason)
        if self._audit:
            await self._audit.log_kick(group_id, target_user_id, admin_id, reason)
        await self._reply(event, f"🔨 Banned and kicked @{target_user_id}: {reason}", line_bot_api)
        return True

    async def _handle_unban_command(self, event, line_bot_api, parts):
        source = event.source
        group_id = source.group_id if source.type == "group" else source.room_id
        admin_id = source.user_id

        if len(parts) < 3:
            await self._reply(event, "Usage: /modmode unban @user_id", line_bot_api)
            return True

        target_user_id = self._get_target_user_id(event, parts)
        if not target_user_id:
            await self._reply(event, "❌ Invalid user ID", line_bot_api)
            return True

        if not await self._is_admin(admin_id):
            await self._reply(event, "❌ Admin only", line_bot_api)
            return True

        success = await self._ban_list.unban_user(group_id, target_user_id)
        if success:
            if self._audit:
                await self._audit.log_mode_change(group_id, admin_id, "unban", True, target_user_id)
            await self._reply(event, f"✅ Unbanned @{target_user_id}", line_bot_api)
        else:
            await self._reply(event, "❌ Failed to unban @{target_user_id} (not found?)", line_bot_api)
        return True

    # ===== Dashboard =====

    async def _show_dashboard(self, event, line_bot_api) -> bool:
        source = event.source
        group_id = source.group_id if source.type == "group" else source.room_id
        info = await self._mod_mode.get_mod_mode_info(group_id) if self._mod_mode else {}

        group_name = f"Group {group_id}" if group_id else "Moderator"
        flex_dict = self._dashboard.build_main_dashboard(group_name, group_id, info or {})

        if self._send_flex_reply:
            await self._send_flex(event, line_bot_api, flex_dict, "Moderator Mode Dashboard")
            return True
        return await self._reply(
            event,
            "Dashboard layout ready; sending dashboards from ModModeAgent is not enabled yet.",
            line_bot_api,
        )

    async def _show_ban_list(self, event, line_bot_api) -> bool:
        source = event.source
        group_id = source.group_id if source.type == "group" else source.room_id
        bans = await self._ban_list.get_ban_list(group_id)
        flex_dict = self._dashboard.build_ban_list_dashboard(group_id, bans)
        await self._send_flex(event, line_bot_api, flex_dict, "Ban List")
        return True

    async def _show_warn_list(self, event, line_bot_api) -> bool:
        source = event.source
        group_id = source.group_id if source.type == "group" else source.room_id
        warnings = await self._warnings.get_warnings(group_id)
        flex_dict = self._dashboard.build_warn_list_dashboard(group_id, warnings)
        await self._send_flex(event, line_bot_api, flex_dict, "Warning List")
        return True

    async def _send_flex(self, event, line_bot_api, flex_dict: dict, alt_text: str) -> None:
        sender = self._send_flex_reply or self._flex_via_reply
        await sender(event, line_bot_api, flex_dict, alt_text)

    async def _flex_via_reply(self, event, line_bot_api, flex_dict: dict, alt_text: str) -> None:
        from linebot.v3.messaging import FlexContainer, FlexMessage

        if not getattr(event, "reply_token", None):
            return

        flex_message = FlexMessage(
            alt_text=alt_text,
            contents=FlexContainer.from_dict(flex_dict),
        )
        await self._reply(
            event,
            flex_message,
            line_bot_api,
            quick_reply=None,
        )

    # ===== Harmful Content =====

    async def _should_detect_harmful(self, group_id: str, text: str) -> bool:
        info = await self._mod_mode.get_mod_mode_info(group_id)
        return info and info.get("mode") == "all"

    async def _handle_harmful_content(self, event: MessageEvent, line_bot_api: MessagingApi, detection):
        source = event.source
        group_id = source.group_id if source.type == "group" else source.room_id
        user_id = source.user_id
        keywords = ", ".join(detection["matched_keywords"])
        return await self._warn_user(event, group_id, user_id, line_bot_api, f"Harmful content: {keywords}")

    # ===== Helpers =====

    async def _is_admin(self, user_id: str) -> bool:
        from src.services.privilege_service import privilege_service

        return privilege_service.is_admin(user_id)

    def _get_target_user_id(self, event, parts: list[str]) -> str | None:
        if hasattr(event.message, "mention") and event.message.mention:
            mentionees = getattr(event.message.mention, "mentionees", [])
            if mentionees:
                return mentionees[0].user_id
        if len(parts) >= 3:
            return parts[2].lstrip("@")
        return None

    async def _reply(self, event, payload, line_bot_api: MessagingApi, quick_reply=None) -> bool:
        from linebot.v3.messaging import ReplyMessageRequest, TextMessage

        if text := payload if isinstance(payload, str) else getattr(payload, "alt_text", ""):
            message = TextMessage(text=text, quick_reply=quick_reply)
        else:
            message = payload

        try:
            reply_token = getattr(event, "reply_token", None)
            if not reply_token:
                return False
            await line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token,
                    [message],
                    notification_disabled=False,
                )
            )
            return True
        except Exception as e:
            logger.error(f"❌ Reply failed: {e}")
            return False
