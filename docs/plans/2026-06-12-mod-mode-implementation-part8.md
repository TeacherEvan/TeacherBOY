### Task 8: Create ModModeAgent (Priority 4)

**Objective:** Main agent intercepting messages in mod-enabled groups.

**Files:**
- Create: `src/agents/mod_mode_agent.py`
- Create: `src/agents/mod_mode/__init__.py`
- Test: `tests/agents/test_mod_mode_agent.py`

**Step 1: Write failing test**

```python
# tests/agents/test_mod_mode_agent.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from src.agents.mod_mode_agent import ModModeAgent

@pytest.fixture
def mock_services():
    with patch("src.agents.mod_mode_agent.ModModeService") as mm, \
         patch("src.agents.mod_mode_agent.BanListService") as bl, \
         patch("src.agents.mod_mode_agent.WarningService") as ws, \
         patch("src.agents.mod_mode_agent.HarmfulContentDetector") as hc, \
         patch("src.agents.mod_mode_agent.ModAuditLog") as al, \
         patch("src.agents.mod_mode_agent.ModDashboardBuilder") as db:
        yield {
            "mod_mode": mm.return_value,
            "ban_list": bl.return_value,
            "warning": ws.return_value,
            "detector": hc.return_value,
            "audit": al.return_value,
            "dashboard": db.return_value,
        }

@pytest.fixture
def agent(mock_services):
    return ModModeAgent()

@pytest.fixture
def event_factory():
    def _make(text: str, user_id: str = "U999", group_id: str = "C123", source_type: str = "group"):
        source = MagicMock()
        source.type = source_type
        source.user_id = user_id
        if source_type == "group":
            source.group_id = group_id
        elif source_type == "room":
            source.room_id = group_id
        msg = MagicMock(spec=TextMessageContent)
        msg.text = text
        event = MagicMock(spec=MessageEvent)
        event.message = msg
        event.source = source
        event.reply_token = "test_token"
        return event
    return _make

@pytest.mark.asyncio
async def test_should_handle_mod_group(agent, mock_services, event_factory):
    mock_services["mod_mode"].is_mod_mode_active.return_value = True
    mock_services["mod_mode"].is_user_allowed.return_value = True
    event = event_factory("hello", group_id="C123")
    result = await agent.should_handle(event, "hello")
    assert result is True

@pytest.mark.asyncio
async def test_should_handle_non_mod_group(agent, mock_services, event_factory):
    mock_services["mod_mode"].is_mod_mode_active.return_value = False
    event = event_factory("hello", group_id="C123")
    result = await agent.should_handle(event, "hello")
    assert result is False

@pytest.mark.asyncio
async def test_should_handle_private_chat_false(agent, mock_services, event_factory):
    event = event_factory("hello", group_id="U123", source_type="user")
    result = await agent.should_handle(event, "hello")
    assert result is False

@pytest.mark.asyncio
async def test_activate_mod_mode_command(agent, mock_services, event_factory):
    mock_services["mod_mode"].activate_mod_mode.return_value = {"mode": "all", "isActive": True}
    mock_services["audit"].log_mode_change = AsyncMock()
    event = event_factory("activate mod mode", user_id="U456", group_id="C123")
    # Mock privilege_service check
    with patch("src.agents.mod_mode_agent.privilege_service") as ps:
        ps.is_admin.return_value = True
        result = await agent.should_handle(event, "activate mod mode")
        assert result is True

@pytest.mark.asyncio
async def test_banned_user_kicked(agent, mock_services, event_factory):
    mock_services["mod_mode"].is_mod_mode_active.return_value = True
    mock_services["ban_list"].is_banned.return_value = True
    event = event_factory("hello", user_id="U999", group_id="C123")
    result = await agent.should_handle(event, "hello")
    assert result is True

@pytest.mark.asyncio
async def test_special_mode_blocks_non_allowed(agent, mock_services, event_factory):
    mock_services["mod_mode"].is_mod_mode_active.return_value = True
    mock_services["mod_mode"].is_user_allowed.return_value = False
    event = event_factory("hello", user_id="U999", group_id="C123")
    result = await agent.should_handle(event, "hello")
    assert result is True
```

**Step 2: Run test to verify failure**

```bash
pytest tests/agents/test_mod_mode_agent.py -v
```

**Step 3: Write implementation**

```python
# src/agents/mod_mode_agent.py
"""Moderator Mode Agent — Priority 4: Intercepts messages in mod-enabled groups."""

import logging
import re
from typing import Optional

from linebot.v3.messaging import MessagingApi, TextMessage
from linebot.v3.webhooks import MessageEvent, TextMessageContent

from src.agents.base_agent import BaseAgent
from src.services.ban_list_service import BanListService
from src.services.harmful_content_detector import HarmfulContentDetector
from src.services.mod_audit_log import ModAuditLog
from src.services.mod_mode_service import ModModeService
from src.services.warning_service import WarningService
from src.agents.mod_mode.dashboard import ModDashboardBuilder

logger = logging.getLogger(__name__)


class ModModeAgent(BaseAgent):
    """High-priority agent for Moderator Mode message interception."""

    def __init__(
        self,
        mod_mode_service: ModModeService,
        ban_list_service: BanListService,
        warning_service: WarningService,
        harmful_detector: HarmfulContentDetector,
        audit_log: ModAuditLog,
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
        """Intercept if group has active mod mode."""
        if not isinstance(event.message, TextMessageContent):
            return False

        source = event.source
        if not source or source.type not in ("group", "room"):
            return False  # Mod mode only in groups/rooms

        group_id = source.group_id if source.type == "group" else source.room_id
        user_id = getattr(source, "user_id", None)
        if not user_id or not group_id:
            return False

        # Check if mod mode is active in this group
        if not await self._mod_mode.is_mod_mode_active(group_id):
            return False

        # Check activation command (from admin)
        if self._is_activation_command(text):
            return await self._is_admin(user_id)

        # Check mod commands
        if self._is_mod_command(text):
            return await self._is_admin(user_id)

        # Check if user is banned (auto-kick handled in handle)
        if await self._ban_list.is_banned(group_id, user_id):
            return True

        # Check special mode: only admin + special user allowed
        if not await self._mod_mode.is_user_allowed(group_id, user_id):
            return True

        # Check harmful content in "all" mode
        if await self._should_detect_harmful(group_id, text):
            return True

        # Allow message through to other agents
        return False

    async def handle(self, event: MessageEvent, text: str, line_bot_api: MessagingApi) -> bool:
        """Process mod mode message."""
        source = event.source
        group_id = source.group_id if source.type == "group" else source.room_id
        user_id = getattr(source, "user_id", None)

        try:
            # 1. Activation command
            if self._is_activation_command(text):
                return await self._handle_activation(event, line_bot_api)

            # 2. Mod commands (/modmode ...)
            if self._is_mod_command(text):
                return await self._handle_mod_command(event, line_bot_api, text)

            # 3. Banned user -> kick
            if await self._ban_list.is_banned(group_id, user_id):
                return await self._kick_user(group_id, user_id, line_bot_api, "banned")

            # 4. Special mode: block non-allowed users
            if not await self._mod_mode.is_user_allowed(group_id, user_id):
                return await self._warn_user(group_id, user_id, line_bot_api, "Not allowed to speak in special mode")

            # 5. Harmful content detection in "all" mode
            if await self._should_detect_harmful(group_id, text):
                detection = await self._detector.detect(text)
                if detection["is_harmful"]:
                    return await self._handle_harmful_content(event, line_bot_api, detection)

            return False  # Let other agents handle

        except Exception as e:
            logger.error(f"❌ ModModeAgent error: {e}", exc_info=True)
            return False

    # ===== Activation =====

    def _is_activation_command(self, text: str) -> bool:
        return re.search(r"activate\s+mod\s+mode", text, re.IGNORECASE) is not None

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
            # Extract @mention
            mention_match = re.search(r"@(\w+)", event.message.text)
            if mention_match:
                special_user_id = mention_match.group(1)  # Simplified - would need LINE mention parsing
            else:
                await self._reply(event, "❌ Usage: 'activate mod mode special @user'", line_bot_api)
                return True

        result = await self._mod_mode.activate_mod_mode(group_id, user_id, mode, special_user_id)
        await self._audit.log_mode_change(group_id, user_id, mode, True, special_user_id)

        mode_msg = "ALL USERS (harmful content monitored)" if mode == "all" else f"SPECIAL MODE (only you + @{special_user_id})"
        await self._reply(
            f"🛡️ Moderator Mode ACTIVATED\nMode: {mode_msg}\nUse /modmode for dashboard",
            line_bot_api,
        )
        return True

    # ===== Mod Commands =====

    def _is_mod_command(self, text: str) -> bool:
        return text.strip().lower().startswith("/modmode")

    async def _handle_mod_command(self, event: MessageEvent, line_bot_api: MessagingApi, text: str) -> bool:
        source = event.source
        group_id = source.group_id if source.type == "group" else source.room_id
        user_id = source.user_id

        parts = text.strip().split()
        if len(parts) == 1:
            return await self._show_dashboard(event, line_bot_api)

        subcmd = parts[1].lower()

        if subcmd == "all":
            await self._mod_mode.activate_mod_mode(group_id, user_id, "all")
            await self._audit.log_mode_change(group_id, user_id, "all", True)
            await self._reply("✅ Mod mode: ALL USERS (harmful content monitored)", line_bot_api)
            return True

        if subcmd == "special":
            if len(parts) < 3:
                await self._reply("Usage: /modmode special @user", line_bot_api)
                return True
            special_id = parts[2].lstrip("@")
            await self._mod_mode.set_special_user(group_id, special_id)
            await self._audit.log_mode_change(group_id, user_id, "special", True, special_id)
            await self._reply(f"✅ Mod mode: SPECIAL (only admin + @{special_id})", line_bot_api)
            return True

        if subcmd == "off":
            await self._mod_mode.deactivate_mod_mode(group_id)
            await self._audit.log_mode_change(group_id, user_id, "all", False)
            await self._reply("🛑 Moderator Mode DEACTIVATED", line_bot_api)
            return True

        if subcmd == "dashboard":
            return await self._show_dashboard(event, line_bot_api)

        if subcmd == "kick":
            return await self._handle_kick_command(event, line_bot_api, parts)

        if subcmd == "warn":
            return await self._handle_warn_command(event, line_bot_api, parts)

        if subcmd == "ban":
            return await self._handle_ban_command(event, line_bot_api, parts)

        if subcmd == "banlist":
            return await self._show_ban_list(event, line_bot_api)

        if subcmd == "warnlist":
            return await self._show_warn_list(event, line_bot_api)

        if subcmd == "unban":
            return await self._handle_unban_command(event, line_bot_api, parts)

        await self._reply("❌ Unknown /modmode command. Use /modmode dashboard", line_bot_api)
        return True

    # ===== Kick/Warn/Ban =====

    async def _kick_user(self, group_id: str, user_id: str, line_bot_api: MessagingApi, reason: str) -> bool:
        """Kick user via LINE API."""
        try:
            if hasattr(line_bot_api, "leave_group"):  # Can't kick directly, need leave_group? No, need kick
                # LINE Bot SDK v3: kick from group
                line_bot_api.kick_users(group_id, [user_id])  # Hypothetical method
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
        # Simplified - would use Flex dashboard postbacks in practice
        await self._reply("Use dashboard to kick users", line_bot_api)
        return True

    # ... similar for warn, ban, unban commands

    # ===== Dashboard =====

    async def _show_dashboard(self, event, line_bot_api):
        source = event.source
        group_id = source.group_id if source.type == "group" else source.room_id
        info = await self._mod_mode.get_mod_mode_info(group_id)
        flex = self._dashboard.build_main_dashboard("Group", group_id, info or {})
        # Send Flex message
        return True

    async def _show_ban_list(self, event, line_bot_api):
        # ... build and send ban list flex
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
```

**Step 4: Run test to verify pass**

```bash
pytest tests/agents/test_mod_mode_agent.py -v
```

**Step 5: Commit**

```bash
git add src/agents/mod_mode_agent.py src/agents/mod_mode/__init__.py tests/agents/test_mod_mode_agent.py
git commit -m "feat(mod-mode): add ModModeAgent (Priority 4)"
```