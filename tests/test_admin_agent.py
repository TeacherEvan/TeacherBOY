"""Tests for admin agent functionality."""

import asyncio
import threading
from unittest.mock import Mock, mock_open, patch

import pytest
from linebot.v3.messaging import FlexMessage, MessagingApi
from linebot.v3.webhooks import MessageEvent

from src.agents.admin_agent import AdminAgent
from src.services.admin_confirmation_service import AdminConfirmationService
from src.services.privilege_service import privilege_service
from src.services.rate_limiter import rate_limiter


@pytest.fixture
def admin_agent():
    """Create admin agent with test configuration."""
    from unittest.mock import Mock

    # Reset privilege_service cache before each test
    privilege_service._reset_for_testing()
    if hasattr(rate_limiter, "reset_admin_destructive_limits_for_testing"):
        rate_limiter.reset_admin_destructive_limits_for_testing()

    with patch("src.agents.admin_agent.settings") as mock_settings:
        mock_settings.get_admin_user_ids.return_value = [
            "U1234567890abcdef",
            "U9876543210fedcba",
        ]
        mock_settings.get_moderator_user_ids.return_value = []

        # Also set privilege_service internal state for tests
        privilege_service._env_admin_user_ids = ["U1234567890abcdef", "U9876543210fedcba"]
        privilege_service._env_moderator_user_ids = []
        privilege_service._settings_loaded = True

        # Create mock http_client for admin agent
        mock_http_client = Mock()
        agent = AdminAgent(http_client=mock_http_client, news_api_key="test_key")
        yield agent

    # Reset after test
    privilege_service._reset_for_testing()
    if hasattr(rate_limiter, "reset_admin_destructive_limits_for_testing"):
        rate_limiter.reset_admin_destructive_limits_for_testing()


@pytest.fixture
def mock_event():
    """Create a mock message event."""
    event = Mock(spec=MessageEvent)
    event.source = Mock()
    event.source.user_id = "U1234567890abcdef"  # Authorized admin
    event.source.group_id = None
    event.source.room_id = None
    event.reply_token = "test_reply_token"
    return event


@pytest.fixture
def mock_line_bot_api():
    """Create a mock LINE Bot API."""
    api = Mock(spec=MessagingApi)
    api.reply_message = Mock()
    api.push_message = Mock()
    api.leave_group = Mock()
    api.leave_room = Mock()
    api.get_message_quota = Mock(return_value={"type": "limited", "value": 1000})
    api.get_message_quota_consumption = Mock(return_value={"totalUsage": 123})
    return api


def _reply_text(api: MessagingApi) -> str:
    return api.reply_message.call_args[0][0].messages[0].text


def _last_reply_text(api: MessagingApi) -> str:
    return api.reply_message.call_args_list[-1][0][0].messages[0].text


def _push_text(api: MessagingApi) -> str:
    return api.push_message.call_args[0][0].messages[0].text


def _reply_message(api: MessagingApi):
    return api.reply_message.call_args[0][0].messages[0]


def _push_message(api: MessagingApi):
    return api.push_message.call_args[0][0].messages[0]


def _collect_button_actions(node):
    if isinstance(node, dict):
        actions = []
        if node.get("type") == "button" and isinstance(node.get("action"), dict):
            actions.append(node["action"])
        for value in node.values():
            actions.extend(_collect_button_actions(value))
        return actions
    if isinstance(node, list):
        actions = []
        for item in node:
            actions.extend(_collect_button_actions(item))
        return actions
    return []


def _flex_action_map(message: FlexMessage) -> dict[str, dict]:
    payload = message.contents.to_dict()
    return {action.get("label", ""): action for action in _collect_button_actions(payload) if action.get("label")}


def _fresh_confirmation_service(token: str = "tok123") -> AdminConfirmationService:
    confirm_service = AdminConfirmationService()
    confirm_service._generate_token = lambda: token  # type: ignore[method-assign]
    return confirm_service


class TestAdminAgent:
    """Test suite for AdminAgent."""

    def test_initialization(self, admin_agent):
        """Test admin agent initialization."""
        assert admin_agent.name == "AdminAgent"
        assert admin_agent.get_priority() == 5  # Highest priority

    def test_is_admin_authorized_user(self, admin_agent):
        """Test that authorized users are recognized as admin."""
        assert admin_agent._is_admin("U1234567890abcdef") is True
        assert admin_agent._is_admin("U9876543210fedcba") is True

    def test_is_admin_unauthorized_user(self, admin_agent):
        """Test that unauthorized users are not recognized as admin."""
        assert admin_agent._is_admin("U0000000000000000") is False
        assert admin_agent._is_admin("random_user") is False

    def test_is_admin_command_valid(self, admin_agent):
        """Test admin command detection with valid commands."""
        assert admin_agent._is_admin_command("/admin help") is True
        assert admin_agent._is_admin_command("/admin status") is True
        assert admin_agent._is_admin_command("!admin help") is True
        assert admin_agent._is_admin_command("/ADMIN HELP") is True
        assert admin_agent._is_admin_command("Dear Ms. Green admin help") is True
        assert admin_agent._is_admin_command("dear ms. green admin status") is True
        assert admin_agent._is_admin_command("Ms. Green admin help") is True

    @pytest.mark.asyncio
    async def test_admin_agent_handles_runtime_alias_admin_command(self, admin_agent):
        assert admin_agent._is_admin_command("Ms. Green admin help") is True

    def test_is_admin_command_invalid(self, admin_agent):
        """Test admin command detection with invalid commands."""
        assert admin_agent._is_admin_command("admin help") is False
        assert admin_agent._is_admin_command("hello") is False
        assert admin_agent._is_admin_command("/not_admin") is False
        assert admin_agent._is_admin_command("RandomWord help") is False

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("Assistant add=U123", ("grant_mod", "U123")),
            ("Assistant add = U123", ("grant_mod", "U123")),
            ('Assistant add = "U123"', ("grant_mod", "U123")),
        ],
    )
    def test_parse_admin_command_assistant_add_variants(self, admin_agent, text, expected):
        """Test Assistant add parsing accepts supported whitespace and quote variants."""
        assert admin_agent._parse_admin_command(text) == expected

    @pytest.mark.asyncio
    async def test_should_handle_authorized_admin_command(self, admin_agent, mock_event):
        """Test that authorized admin commands are handled."""
        result = await admin_agent.should_handle(mock_event, "/admin help")
        assert result is True

    @pytest.mark.asyncio
    async def test_should_handle_unauthorized_user(self, admin_agent, mock_event):
        """Test that unauthorized users' admin commands are not handled."""
        mock_event.source.user_id = "U0000000000000000"  # Unauthorized
        result = await admin_agent.should_handle(mock_event, "/admin help")
        assert result is False

    @pytest.mark.asyncio
    async def test_should_handle_assistant_add_non_admin_user(self, admin_agent, mock_event):
        """Test that non-admin users cannot trigger Assistant add moderator commands."""
        mock_event.source.user_id = "U0000000000000000"

        result = await admin_agent.should_handle(mock_event, 'Assistant add = "U123"')

        assert result is False

    @pytest.mark.asyncio
    async def test_handle_assistant_add_normalizes_user_id_for_authorized_admin(
        self, admin_agent, mock_event, mock_line_bot_api
    ):
        """Test Assistant add grants moderator via normalized ID without leaking state."""
        assert await admin_agent.should_handle(mock_event, 'Assistant add = "U123"') is True

        try:
            mocked_open = mock_open()
            with patch("os.makedirs") as mock_makedirs, patch("builtins.open", mocked_open):
                result = await admin_agent.handle(
                    mock_event,
                    'Assistant add = "U123"',
                    mock_line_bot_api,
                )

            assert result is True
            mock_makedirs.assert_called_once_with("data", exist_ok=True)
            mocked_open.assert_called_once_with("data/moderators.json", "w")
            assert privilege_service.is_moderator("U123") is True
            mock_line_bot_api.reply_message.assert_called_once()

            call_args = mock_line_bot_api.reply_message.call_args
            message_text = call_args[0][0].messages[0].text
            assert "U123" in message_text
            assert '"U123"' not in message_text
        finally:
            privilege_service._claimed_moderator_user_ids.discard("U123")

    @pytest.mark.asyncio
    async def test_should_handle_non_admin_command(self, admin_agent, mock_event):
        """Test that non-admin commands are not handled."""
        result = await admin_agent.should_handle(mock_event, "hello world")
        assert result is False

    @pytest.mark.asyncio
    async def test_handle_help_command(self, admin_agent, mock_event, mock_line_bot_api):
        """Test /admin help command."""
        result = await admin_agent.handle(mock_event, "/admin help", mock_line_bot_api)

        assert result is True
        mock_line_bot_api.reply_message.assert_called_once()

        # Check that help text contains key commands
        call_args = mock_line_bot_api.reply_message.call_args
        message_text = call_args[0][0].messages[0].text
        assert "status" in message_text.lower()
        assert "wake" in message_text.lower()
        assert "sleep" in message_text.lower()
        assert "reset" in message_text.lower()
        assert "request resetting chat session & history" in message_text.lower()
        assert "private confirmation required" in message_text.lower()
        assert "dear ms. green admin <command>" in message_text.lower()
        assert "dear zeus" not in message_text.lower()
        assert "purge" in message_text.lower()
        assert message_text.lower().count("private confirmation required") >= 2
        assert "3 destructive requests per 10 minutes" in message_text.lower()

    @pytest.mark.asyncio
    async def test_handle_status_command_via_ms_green_alias(self, admin_agent, mock_event, mock_line_bot_api):
        """Smoke test the natural-language admin alias through central dispatch."""
        with patch("src.agents.admin_agent.session_manager") as mock_session_mgr:
            mock_session_mgr.is_session_active.return_value = False
            mock_session_mgr.is_sleeping.return_value = False
            mock_session_mgr.get_sleep_remaining.return_value = 0
            mock_session_mgr.get_session_info.return_value = {}

            result = await admin_agent.handle(
                mock_event,
                "Dear Ms. Green admin status",
                mock_line_bot_api,
            )

            assert result is True
            mock_line_bot_api.reply_message.assert_called_once()

            message_text = _reply_text(mock_line_bot_api)
            assert "status" in message_text.lower()
            assert "chat id" in message_text.lower()

    @pytest.mark.asyncio
    async def test_handle_status_command(self, admin_agent, mock_event, mock_line_bot_api):
        """Test /admin status command."""
        with patch("src.agents.admin_agent.session_manager") as mock_session_mgr:
            mock_session_mgr.is_session_active.return_value = False
            mock_session_mgr.is_sleeping.return_value = False
            mock_session_mgr.get_sleep_remaining.return_value = 0
            mock_session_mgr.get_session_info.return_value = {}

            result = await admin_agent.handle(mock_event, "/admin status", mock_line_bot_api)

            assert result is True
            mock_line_bot_api.reply_message.assert_called_once()

            # Check response contains status information
            call_args = mock_line_bot_api.reply_message.call_args
            message_text = call_args[0][0].messages[0].text
            assert "Status" in message_text
            assert "Chat ID" in message_text

    @pytest.mark.asyncio
    async def test_handle_wake_command(self, admin_agent, mock_event, mock_line_bot_api):
        """Test /admin wake command."""
        with patch("src.agents.admin_agent.session_manager") as mock_session_mgr:
            mock_session_mgr.is_sleeping.return_value = True
            mock_session_mgr.wake_chat.return_value = True

            result = await admin_agent.handle(mock_event, "/admin wake", mock_line_bot_api)

            assert result is True
            mock_session_mgr.wake_chat.assert_called_once()
            mock_line_bot_api.reply_message.assert_called_once()

            call_args = mock_line_bot_api.reply_message.call_args
            message_text = call_args[0][0].messages[0].text
            assert "woken" in message_text.lower() or "wake" in message_text.lower()

    @pytest.mark.asyncio
    async def test_handle_sleep_command(self, admin_agent, mock_event, mock_line_bot_api):
        """Test /admin sleep command."""
        with patch("src.agents.admin_agent.session_manager") as mock_session_mgr:
            result = await admin_agent.handle(mock_event, "/admin sleep 12", mock_line_bot_api)

            assert result is True
            # Check that sleep_chat was called with correct hours
            mock_session_mgr.sleep_chat.assert_called_once()
            call_args = mock_session_mgr.sleep_chat.call_args
            # Should be called with chat_id and hours
            assert call_args[0][1] == 12 or call_args[1].get("hours") == 12

    @pytest.mark.asyncio
    async def test_handle_reset_command(self, admin_agent, mock_event, mock_line_bot_api):
        """Test /admin reset command."""
        confirm_service = _fresh_confirmation_service("reset-command-123")

        with (
            patch("src.agents.admin_agent.admin_confirmation_service", confirm_service),
            patch("src.agents.admin_agent.session_manager") as mock_session_mgr,
        ):
            mock_session_mgr.end_session.return_value = True
            mock_session_mgr.wake_chat.return_value = False

            result = await admin_agent.handle(mock_event, "/admin reset", mock_line_bot_api)

            assert result is True
            mock_session_mgr.end_session.assert_not_called()
            mock_session_mgr.clear_message_history.assert_not_called()
            mock_session_mgr.wake_chat.assert_not_called()
            mock_line_bot_api.push_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_reset_requests_private_confirmation_instead_of_executing_immediately(
        self, admin_agent, mock_event, mock_line_bot_api
    ):
        confirm_service = _fresh_confirmation_service("reset123")

        with (
            patch("src.agents.admin_agent.admin_confirmation_service", confirm_service),
            patch("src.agents.admin_agent.session_manager") as mock_session_mgr,
        ):
            ok = await admin_agent.handle(mock_event, "/admin reset", mock_line_bot_api)

        assert ok is True
        mock_session_mgr.end_session.assert_not_called()
        mock_session_mgr.clear_message_history.assert_not_called()
        mock_session_mgr.wake_chat.assert_not_called()
        assert confirm_service.count_pending() == 1
        mock_line_bot_api.push_message.assert_called_once()
        assert "private" in _reply_text(mock_line_bot_api).lower()

        preview_text = _push_text(mock_line_bot_api)
        assert "user_U1234567890abcdef" in preview_text
        assert "reset" in preview_text.lower()
        assert "history" in preview_text.lower()

    @pytest.mark.asyncio
    async def test_handle_sessions_command(self, admin_agent, mock_event, mock_line_bot_api):
        """Test /admin sessions command."""
        with patch("src.agents.admin_agent.session_manager") as mock_session_mgr:
            # Mock active sessions using public method
            mock_session_mgr.get_active_sessions.return_value = {"user_U123": {"user_id": "U123", "message_count": 5}}
            mock_session_mgr.get_sleeping_chats.return_value = {}

            result = await admin_agent.handle(mock_event, "/admin sessions", mock_line_bot_api)

            assert result is True
            mock_line_bot_api.reply_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_groups_command(self, admin_agent, mock_event, mock_line_bot_api):
        """Test /admin groups command."""
        with patch("src.services.group_membership_service.group_membership_service") as mock_group_mgr:
            mock_group_mgr.get_groups_list.return_value = [
                {"chat_id": "C123", "type": "group", "title": "Test Group"},
                {"chat_id": "R456", "type": "room", "title": "Test Room"},
            ]
            mock_group_mgr.get_count.return_value = (1, 1)

            result = await admin_agent.handle(mock_event, "/admin groups", mock_line_bot_api)

            assert result is True
            mock_line_bot_api.reply_message.assert_called_once()
            message = _reply_message(mock_line_bot_api)
            assert "Test Group" in message.text
            assert "Test Room" in message.text
            assert "group_C123" in message.text
            assert "room_R456" in message.text

    @pytest.mark.asyncio
    async def test_dashboard_in_private_chat_returns_flex_message(self, admin_agent, mock_event, mock_line_bot_api):
        ok = await admin_agent.handle(mock_event, "/admin dashboard", mock_line_bot_api)

        assert ok is True
        mock_line_bot_api.reply_message.assert_called_once()
        mock_line_bot_api.push_message.assert_not_called()

        message = _reply_message(mock_line_bot_api)
        assert isinstance(message, FlexMessage)
        action_map = _flex_action_map(message)
        assert "View status" in action_map
        assert "Toggle sleep/wake" in action_map
        assert "Open confirmations" in action_map
        assert "View sessions" in action_map

    @pytest.mark.asyncio
    async def test_dashboard_in_group_pushes_private_dashboard_and_replies_neutrally(
        self, admin_agent, mock_event, mock_line_bot_api
    ):
        mock_event.source.group_id = "C123456"
        mock_event.source.room_id = None

        ok = await admin_agent.handle(mock_event, "/admin dashboard", mock_line_bot_api)

        assert ok is True
        mock_line_bot_api.reply_message.assert_called_once()
        mock_line_bot_api.push_message.assert_called_once()
        assert "sent your admin panel privately" in _reply_text(mock_line_bot_api).lower()
        assert isinstance(_push_message(mock_line_bot_api), FlexMessage)

    @pytest.mark.asyncio
    async def test_dashboard_safe_actions_are_direct_buttons(self, admin_agent, mock_event, mock_line_bot_api):
        ok = await admin_agent.handle(mock_event, "/admin dashboard", mock_line_bot_api)

        assert ok is True
        action_map = _flex_action_map(_reply_message(mock_line_bot_api))

        assert action_map["View status"]["type"] == "message"
        assert action_map["View status"]["text"] == "/admin status user_U1234567890abcdef"
        assert action_map["Toggle sleep/wake"]["type"] == "message"
        assert action_map["Toggle sleep/wake"]["text"] == "/admin sleep user_U1234567890abcdef 24"
        assert action_map["Open confirmations"]["type"] == "message"
        assert action_map["Open confirmations"]["text"] == "/admin confirmations"
        assert action_map["View sessions"]["type"] == "message"
        assert action_map["View sessions"]["text"] == "/admin sessions"

    @pytest.mark.asyncio
    async def test_dashboard_risky_actions_open_preview_only_commands(self, admin_agent, mock_event, mock_line_bot_api):
        mock_event.source.group_id = "C123456"
        mock_event.source.room_id = None

        ok = await admin_agent.handle(mock_event, "/admin dashboard", mock_line_bot_api)

        assert ok is True
        action_map = _flex_action_map(_push_message(mock_line_bot_api))

        assert action_map["Preview reset"]["type"] == "message"
        assert action_map["Preview reset"]["text"] == "/admin reset group_C123456"
        assert action_map["Preview purge"]["type"] == "message"
        assert action_map["Preview purge"]["text"] == "/admin purge group_C123456"
        assert action_map["Preview leave"]["type"] == "message"
        assert action_map["Preview leave"]["text"] == "/admin leave group_C123456"

    @pytest.mark.asyncio
    async def test_dashboard_displays_current_persistence_backend_without_switch_control(
        self, admin_agent, mock_event, mock_line_bot_api
    ):
        with patch("src.agents.admin_agent.settings.persistence_backend", "convex"):
            ok = await admin_agent.handle(mock_event, "/admin dashboard", mock_line_bot_api)

        assert ok is True
        message = _reply_message(mock_line_bot_api)
        payload = message.contents.to_dict()
        payload_text = str(payload).lower()
        assert "convex" in payload_text
        assert "switch backend" not in payload_text
        assert "/admin backend" not in payload_text
        assert "persistence backend" in payload_text

    @pytest.mark.asyncio
    async def test_confirmations_command_is_private_chat_only(self, admin_agent, mock_event, mock_line_bot_api):
        confirm_service = _fresh_confirmation_service("confirmations123")
        mock_event.source.group_id = "C123456"
        mock_event.source.room_id = None

        with patch("src.agents.admin_agent.admin_confirmation_service", confirm_service):
            request_ok = await admin_agent.handle(
                mock_event,
                "/admin purge",
                mock_line_bot_api,
            )
            assert request_ok is True

            mock_line_bot_api.reply_message.reset_mock()
            mock_line_bot_api.push_message.reset_mock()

            confirmations_ok = await admin_agent.handle(
                mock_event,
                "/admin confirmations",
                mock_line_bot_api,
            )

        assert confirmations_ok is True
        reply_text = _reply_text(mock_line_bot_api).lower()
        assert "private chat" in reply_text
        assert "confirmations123" not in reply_text
        assert "group_c123456" not in reply_text

    @pytest.mark.asyncio
    async def test_handle_unknown_command(self, admin_agent, mock_event, mock_line_bot_api):
        """Test handling of unknown admin command."""
        result = await admin_agent.handle(mock_event, "/admin unknown_cmd", mock_line_bot_api)

        assert result is True
        mock_line_bot_api.reply_message.assert_called_once()

        # Check response indicates unknown command
        call_args = mock_line_bot_api.reply_message.call_args
        message_text = call_args[0][0].messages[0].text
        assert "Unknown command" in message_text or "unknown" in message_text.lower()

    @pytest.mark.asyncio
    async def test_get_chat_id_from_user(self, admin_agent, mock_event):
        """Test extracting chat ID from user event."""
        mock_event.source.user_id = "U123456"
        mock_event.source.group_id = None
        mock_event.source.room_id = None

        chat_id = admin_agent._get_chat_id(mock_event)
        assert chat_id == "user_U123456"

    @pytest.mark.asyncio
    async def test_get_chat_id_from_group(self, admin_agent, mock_event):
        """Test extracting chat ID from group event."""
        mock_event.source.group_id = "C123456"

        chat_id = admin_agent._get_chat_id(mock_event)
        assert chat_id == "group_C123456"

    @pytest.mark.asyncio
    async def test_handle_leave_current_group(self, admin_agent, mock_event, mock_line_bot_api):
        """Test /admin leave requests confirmation (does not leave immediately)."""
        mock_event.source.group_id = "C123456"
        mock_event.source.room_id = None

        confirm_service = AdminConfirmationService()
        confirm_service._generate_token = lambda: "tok123"  # type: ignore[method-assign]
        with patch("src.agents.admin_agent.admin_confirmation_service", confirm_service):
            ok = await admin_agent.handle(mock_event, "/admin leave", mock_line_bot_api)
        assert ok is True
        mock_line_bot_api.reply_message.assert_called_once()
        mock_line_bot_api.push_message.assert_called_once()
        mock_line_bot_api.leave_group.assert_not_called()

    @pytest.mark.asyncio
    async def test_group_leave_request_replies_neutrally_and_sends_preview_to_dm(
        self, admin_agent, mock_event, mock_line_bot_api
    ):
        mock_event.source.group_id = "C123456"
        mock_event.source.room_id = None

        confirm_service = _fresh_confirmation_service("leave123")
        with patch("src.agents.admin_agent.admin_confirmation_service", confirm_service):
            ok = await admin_agent.handle(mock_event, "/admin leave", mock_line_bot_api)

        assert ok is True
        group_reply = _reply_text(mock_line_bot_api)
        assert "leave123" not in group_reply
        assert "/admin confirm" not in group_reply.lower()
        assert "C123456" not in group_reply

        preview_text = _push_text(mock_line_bot_api)
        assert "C123456" in preview_text
        assert "leave" in preview_text.lower()
        assert "group" in preview_text.lower()

    @pytest.mark.asyncio
    async def test_handle_leave_specific_group_chat_id(self, admin_agent, mock_event, mock_line_bot_api):
        """Test /admin leave group_<id> requests confirmation."""
        # Simulate running the command from anywhere
        mock_event.source.group_id = None
        mock_event.source.room_id = None

        confirm_service = AdminConfirmationService()
        confirm_service._generate_token = lambda: "tok123"  # type: ignore[method-assign]
        with patch("src.agents.admin_agent.admin_confirmation_service", confirm_service):
            ok = await admin_agent.handle(mock_event, "/admin leave group_C999", mock_line_bot_api)
        assert ok is True
        mock_line_bot_api.reply_message.assert_called_once()
        mock_line_bot_api.push_message.assert_called_once()
        mock_line_bot_api.leave_group.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_leave_invalid_in_user_chat(self, admin_agent, mock_event, mock_line_bot_api):
        """Test /admin leave errors in 1:1 chat without a target."""
        mock_event.source.group_id = None
        mock_event.source.room_id = None

        ok = await admin_agent.handle(mock_event, "/admin leave", mock_line_bot_api)
        assert ok is True
        mock_line_bot_api.reply_message.assert_called_once()
        mock_line_bot_api.leave_group.assert_not_called()
        mock_line_bot_api.leave_room.assert_not_called()

    @pytest.mark.asyncio
    async def test_confirm_executes_leave_in_private_chat(self, admin_agent, mock_event, mock_line_bot_api):
        """Test /admin confirm executes the pending leave action when run in private chat."""
        confirm_service = AdminConfirmationService()
        confirm_service._generate_token = lambda: "tok123"  # type: ignore[method-assign]

        # Request leave for a specific group
        mock_event.source.group_id = None
        mock_event.source.room_id = None
        with patch("src.agents.admin_agent.admin_confirmation_service", confirm_service):
            ok = await admin_agent.handle(mock_event, "/admin leave group_C999", mock_line_bot_api)
            assert ok is True

            # Confirm in private chat (user_*)
            confirm_event = Mock(spec=MessageEvent)
            confirm_event.source = Mock()
            confirm_event.source.user_id = mock_event.source.user_id
            confirm_event.source.group_id = None
            confirm_event.source.room_id = None
            confirm_event.reply_token = "confirm_reply_token"

            ok2 = await admin_agent.handle(confirm_event, "/admin confirm tok123", mock_line_bot_api)
            assert ok2 is True
            mock_line_bot_api.leave_group.assert_called_once_with("C999")

    @pytest.mark.asyncio
    async def test_group_purge_request_does_not_echo_token_or_target_in_group_reply(
        self, admin_agent, mock_event, mock_line_bot_api
    ):
        mock_event.source.group_id = "C123456"
        mock_event.source.room_id = None

        confirm_service = _fresh_confirmation_service("purge123")
        with patch("src.agents.admin_agent.admin_confirmation_service", confirm_service):
            ok = await admin_agent.handle(mock_event, "/admin purge", mock_line_bot_api)

        assert ok is True
        group_reply = _reply_text(mock_line_bot_api)
        assert "purge123" not in group_reply
        assert "/admin confirm" not in group_reply.lower()
        assert "group_C123456" not in group_reply
        assert "C123456" not in group_reply

        preview_text = _push_text(mock_line_bot_api)
        assert "group_C123456" in preview_text
        assert "history" in preview_text.lower()

    @pytest.mark.asyncio
    async def test_push_failure_does_not_arm_destructive_action(self, admin_agent, mock_event, mock_line_bot_api):
        confirm_service = _fresh_confirmation_service("fail123")
        mock_line_bot_api.push_message.side_effect = RuntimeError("push failed")

        with patch("src.agents.admin_agent.admin_confirmation_service", confirm_service):
            ok = await admin_agent.handle(mock_event, "/admin purge", mock_line_bot_api)

        assert ok is True
        reply_text = _reply_text(mock_line_bot_api)
        assert "private preview" in reply_text.lower()
        assert "fail123" not in reply_text
        assert "/admin confirm" not in reply_text.lower()
        assert confirm_service.count_pending() == 0
        assert rate_limiter._admin_destructive_targets == {}

    @pytest.mark.asyncio
    async def test_confirm_in_group_is_rejected_and_does_not_execute(self, admin_agent, mock_event, mock_line_bot_api):
        confirm_service = _fresh_confirmation_service("groupconfirm123")

        with patch("src.agents.admin_agent.admin_confirmation_service", confirm_service):
            ok = await admin_agent.handle(mock_event, "/admin leave group_C999", mock_line_bot_api)
            assert ok is True

            mock_line_bot_api.reply_message.reset_mock()
            mock_line_bot_api.push_message.reset_mock()

            mock_event.source.group_id = "C123456"
            confirm_ok = await admin_agent.handle(mock_event, "/admin confirm groupconfirm123", mock_line_bot_api)

        assert confirm_ok is True
        assert "private chat" in _reply_text(mock_line_bot_api).lower()
        mock_line_bot_api.leave_group.assert_not_called()
        assert confirm_service.count_pending() == 1

    @pytest.mark.asyncio
    async def test_confirm_with_other_admins_token_is_rejected(self, admin_agent, mock_event, mock_line_bot_api):
        confirm_service = _fresh_confirmation_service("otheradmin123")

        with patch("src.agents.admin_agent.admin_confirmation_service", confirm_service):
            first_ok = await admin_agent.handle(
                mock_event,
                "/admin leave group_C999",
                mock_line_bot_api,
            )
            assert first_ok is True

            mock_line_bot_api.reply_message.reset_mock()
            mock_line_bot_api.push_message.reset_mock()

            other_admin_event = Mock(spec=MessageEvent)
            other_admin_event.source = Mock()
            other_admin_event.source.user_id = "U9876543210fedcba"
            other_admin_event.source.group_id = None
            other_admin_event.source.room_id = None
            other_admin_event.reply_token = "other_admin_reply_token"

            confirm_ok = await admin_agent.handle(
                other_admin_event,
                "/admin confirm otheradmin123",
                mock_line_bot_api,
            )

        assert confirm_ok is True
        assert "another admin" in _reply_text(mock_line_bot_api).lower()
        mock_line_bot_api.leave_group.assert_not_called()
        assert confirm_service.count_pending() == 1

    @pytest.mark.asyncio
    async def test_confirm_rejects_unknown_or_expired_token(self, admin_agent, mock_event, mock_line_bot_api):
        confirm_service = _fresh_confirmation_service("expired123")

        with patch("src.agents.admin_agent.admin_confirmation_service", confirm_service):
            request_ok = await admin_agent.handle(
                mock_event,
                "/admin reset",
                mock_line_bot_api,
            )
            assert request_ok is True
            assert confirm_service.count_pending() == 1

            confirm_service.cancel("expired123", mock_event.source.user_id)
            mock_line_bot_api.reply_message.reset_mock()
            mock_line_bot_api.push_message.reset_mock()

            confirm_ok = await admin_agent.handle(
                mock_event,
                "/admin confirm expired123",
                mock_line_bot_api,
            )

        assert confirm_ok is True
        assert "unknown or expired" in _reply_text(mock_line_bot_api).lower()
        assert confirm_service.count_pending() == 0

    @pytest.mark.asyncio
    async def test_cancel_in_group_is_rejected_and_does_not_cancel(self, admin_agent, mock_event, mock_line_bot_api):
        confirm_service = _fresh_confirmation_service("groupcancel123")

        with patch("src.agents.admin_agent.admin_confirmation_service", confirm_service):
            request_ok = await admin_agent.handle(
                mock_event,
                "/admin leave group_C999",
                mock_line_bot_api,
            )
            assert request_ok is True
            assert confirm_service.count_pending() == 1

            mock_line_bot_api.reply_message.reset_mock()
            mock_line_bot_api.push_message.reset_mock()
            mock_event.source.group_id = "C123456"

            cancel_ok = await admin_agent.handle(
                mock_event,
                "/admin cancel groupcancel123",
                mock_line_bot_api,
            )

        assert cancel_ok is True
        assert "private chat" in _reply_text(mock_line_bot_api).lower()
        assert confirm_service.count_pending() == 1

    @pytest.mark.asyncio
    async def test_confirm_in_private_chat_executes_matching_reset_action(self, admin_agent, mock_event, mock_line_bot_api):
        confirm_service = _fresh_confirmation_service("resetconfirm123")

        with (
            patch("src.agents.admin_agent.admin_confirmation_service", confirm_service),
            patch("src.agents.admin_agent.session_manager") as mock_session_mgr,
        ):
            mock_session_mgr.end_session.return_value = True
            mock_session_mgr.wake_chat.return_value = False

            ok = await admin_agent.handle(mock_event, "/admin reset", mock_line_bot_api)
            assert ok is True

            mock_line_bot_api.reply_message.reset_mock()
            mock_line_bot_api.push_message.reset_mock()

            confirm_ok = await admin_agent.handle(mock_event, "/admin confirm resetconfirm123", mock_line_bot_api)

        assert confirm_ok is True
        mock_session_mgr.end_session.assert_called_once_with("user_U1234567890abcdef")
        mock_session_mgr.clear_message_history.assert_called_once_with("user_U1234567890abcdef")
        mock_session_mgr.wake_chat.assert_called_once_with("user_U1234567890abcdef")
        assert "reset complete" in _reply_text(mock_line_bot_api).lower()

    @pytest.mark.asyncio
    async def test_second_destructive_request_for_same_target_is_blocked_by_reservation(
        self, admin_agent, mock_event, mock_line_bot_api
    ):
        confirm_service = AdminConfirmationService()
        tokens = iter(["first123", "second123"])
        confirm_service._generate_token = lambda: next(tokens)  # type: ignore[method-assign]
        mock_event.source.group_id = "C123456"
        mock_event.source.room_id = None

        with patch("src.agents.admin_agent.admin_confirmation_service", confirm_service):
            first_ok = await admin_agent.handle(mock_event, "/admin purge", mock_line_bot_api)
            assert first_ok is True

            mock_line_bot_api.reply_message.reset_mock()
            mock_line_bot_api.push_message.reset_mock()

            second_ok = await admin_agent.handle(mock_event, "/admin reset", mock_line_bot_api)

        assert second_ok is True
        assert "already pending" in _reply_text(mock_line_bot_api).lower()
        assert "too many destructive admin requests" not in _reply_text(mock_line_bot_api).lower()
        mock_line_bot_api.push_message.assert_not_called()
        assert confirm_service.count_pending() == 1

    @pytest.mark.asyncio
    async def test_same_target_is_reserved_before_preview_push_returns(self, admin_agent, mock_event, mock_line_bot_api):
        confirm_service = AdminConfirmationService()
        tokens = iter(["flight123", "flight456"])
        confirm_service._generate_token = lambda: next(tokens)  # type: ignore[method-assign]
        preview_started = threading.Event()
        release_preview = threading.Event()
        push_calls = 0

        def block_first_preview(*args, **kwargs):
            nonlocal push_calls
            push_calls += 1
            if push_calls == 1:
                preview_started.set()
                release_preview.wait(timeout=2)

        mock_event.source.group_id = None
        mock_event.source.room_id = None
        mock_line_bot_api.push_message.side_effect = block_first_preview

        with patch("src.agents.admin_agent.admin_confirmation_service", confirm_service):
            first_request = asyncio.create_task(
                admin_agent.handle(
                    mock_event,
                    "/admin leave group_C999",
                    mock_line_bot_api,
                )
            )

            assert await asyncio.to_thread(preview_started.wait, 1.0) is True

            second_ok = await admin_agent.handle(
                mock_event,
                "/admin leave group_C999",
                mock_line_bot_api,
            )
            second_reply = _last_reply_text(mock_line_bot_api)
            assert confirm_service.count_pending() == 0

            release_preview.set()
            first_ok = await first_request

        assert first_ok is True
        assert second_ok is True
        assert "already pending" in second_reply.lower()
        assert confirm_service.count_pending() == 1

    @pytest.mark.asyncio
    async def test_invalid_explicit_purge_and_reset_targets_are_rejected(self, admin_agent, mock_event, mock_line_bot_api):
        confirm_service = _fresh_confirmation_service("invalid123")

        with patch("src.agents.admin_agent.admin_confirmation_service", confirm_service):
            purge_ok = await admin_agent.handle(
                mock_event,
                "/admin purge C999",
                mock_line_bot_api,
            )

            reset_ok = await admin_agent.handle(
                mock_event,
                "/admin reset foo",
                mock_line_bot_api,
            )

        assert purge_ok is True
        assert reset_ok is True
        assert "invalid target" in mock_line_bot_api.reply_message.call_args_list[0][0][0].messages[0].text.lower()
        assert "invalid target" in mock_line_bot_api.reply_message.call_args_list[1][0][0].messages[0].text.lower()
        mock_line_bot_api.push_message.assert_not_called()
        assert confirm_service.count_pending() == 0

    def test_purge_clears_calendar_session_and_message_buffer(self, admin_agent):
        calendar_session_manager = Mock()
        calendar_session_manager.get_session.return_value = object()
        message_buffer_service = Mock()
        message_buffer_service.clear_chat_buffer.return_value = 3

        with (
            patch("src.agents.admin_agent.session_manager") as mock_session_mgr,
            patch(
                "src.services.calendar_session_manager.calendar_session_manager",
                calendar_session_manager,
            ),
            patch(
                "src.services.message_buffer_service.message_buffer_service",
                message_buffer_service,
            ),
        ):
            mock_session_mgr.end_session.return_value = True
            mock_session_mgr.wake_chat.return_value = False
            result = admin_agent._purge_chat("group_C123", "group_C123")

        calendar_session_manager.end_session.assert_called_once_with("group_C123")
        message_buffer_service.clear_chat_buffer.assert_called_once_with("group_C123")
        assert "calendar flow: ended" in result.lower()
        assert "message buffer: cleared 3 message(s)" in result.lower()

    @pytest.mark.asyncio
    async def test_same_target_can_be_rearmed_after_cancel(self, admin_agent, mock_event, mock_line_bot_api):
        confirm_service = AdminConfirmationService()
        tokens = iter(["cancel123", "cancel456"])
        confirm_service._generate_token = lambda: next(tokens)  # type: ignore[method-assign]
        mock_event.source.group_id = None
        mock_event.source.room_id = None

        with patch("src.agents.admin_agent.admin_confirmation_service", confirm_service):
            first_ok = await admin_agent.handle(
                mock_event,
                "/admin leave group_C999",
                mock_line_bot_api,
            )
            assert first_ok is True
            assert confirm_service.count_pending() == 1

            mock_line_bot_api.reply_message.reset_mock()
            mock_line_bot_api.push_message.reset_mock()

            cancel_ok = await admin_agent.handle(
                mock_event,
                "/admin cancel cancel123",
                mock_line_bot_api,
            )

            assert cancel_ok is True
            assert "cancelled" in _reply_text(mock_line_bot_api).lower()
            assert confirm_service.count_pending() == 0

            mock_line_bot_api.reply_message.reset_mock()
            mock_line_bot_api.push_message.reset_mock()

            second_ok = await admin_agent.handle(
                mock_event,
                "/admin leave group_C999",
                mock_line_bot_api,
            )

        assert second_ok is True
        assert "private preview sent" in _reply_text(mock_line_bot_api).lower()
        mock_line_bot_api.push_message.assert_called_once()
        assert confirm_service.count_pending() == 1

    @pytest.mark.asyncio
    async def test_same_target_can_be_rearmed_after_confirm(self, admin_agent, mock_event, mock_line_bot_api):
        confirm_service = AdminConfirmationService()
        tokens = iter(["confirm123", "confirm456"])
        confirm_service._generate_token = lambda: next(tokens)  # type: ignore[method-assign]
        mock_event.source.group_id = None
        mock_event.source.room_id = None

        with patch("src.agents.admin_agent.admin_confirmation_service", confirm_service):
            first_ok = await admin_agent.handle(
                mock_event,
                "/admin leave group_C999",
                mock_line_bot_api,
            )
            assert first_ok is True

            mock_line_bot_api.reply_message.reset_mock()
            mock_line_bot_api.push_message.reset_mock()

            confirm_ok = await admin_agent.handle(
                mock_event,
                "/admin confirm confirm123",
                mock_line_bot_api,
            )

            assert confirm_ok is True
            assert "left group c999" in _reply_text(mock_line_bot_api).lower()
            assert confirm_service.count_pending() == 0

            mock_line_bot_api.reply_message.reset_mock()
            mock_line_bot_api.push_message.reset_mock()

            second_ok = await admin_agent.handle(
                mock_event,
                "/admin leave group_C999",
                mock_line_bot_api,
            )

        assert second_ok is True
        assert "private preview sent" in _reply_text(mock_line_bot_api).lower()
        mock_line_bot_api.push_message.assert_called_once()
        mock_line_bot_api.leave_group.assert_called_once_with("C999")
        assert confirm_service.count_pending() == 1

    @pytest.mark.asyncio
    async def test_admin_destructive_quota_blocks_fourth_distinct_target(self, admin_agent, mock_event, mock_line_bot_api):
        confirm_service = AdminConfirmationService()
        tokens = iter(["quota1", "quota2", "quota3", "quota4"])
        confirm_service._generate_token = lambda: next(tokens)  # type: ignore[method-assign]

        with patch("src.agents.admin_agent.admin_confirmation_service", confirm_service):
            for target_chat_id in ("group_C100", "group_C101", "group_C102"):
                ok = await admin_agent.handle(
                    mock_event,
                    f"/admin leave {target_chat_id}",
                    mock_line_bot_api,
                )

                assert ok is True
                assert "private preview sent" in _last_reply_text(mock_line_bot_api).lower()

                mock_line_bot_api.reply_message.reset_mock()
                mock_line_bot_api.push_message.reset_mock()

            fourth_ok = await admin_agent.handle(
                mock_event,
                "/admin leave group_C103",
                mock_line_bot_api,
            )

        assert fourth_ok is True
        assert "too many destructive admin requests" in _reply_text(mock_line_bot_api).lower()
        assert "already pending" not in _reply_text(mock_line_bot_api).lower()
        mock_line_bot_api.push_message.assert_not_called()
        assert confirm_service.count_pending() == 3

    @pytest.mark.asyncio
    async def test_stats_command(self, admin_agent, mock_event, mock_line_bot_api):
        """Test /admin stats returns enhanced dashboard response."""
        with (
            patch("src.agents.admin_agent.session_manager") as mock_session_mgr,
            patch("src.agents.admin_agent.metrics_service") as mock_metrics,
        ):
            mock_session_mgr.get_active_sessions.return_value = {}
            mock_session_mgr.get_sleeping_chats.return_value = {}

            # Mock metrics snapshot with enhanced data
            from datetime import datetime

            from src.services.metrics_service import MetricsSnapshot

            mock_snapshot = MetricsSnapshot(
                started_at=datetime.utcnow(),
                translation_requests_total=100,
                translation_google_total=80,
                translation_libre_total=20,
                news_requests_total=50,
                last_friend_added_at=None,
                last_friend_added_user_id=None,
                friends_follow_events_total=12,
                friends_unfollow_events_total=3,
                rate_limited_requests=5,
                failed_translations=3,
                admin_commands_total=10,
                unique_users_count=25,
                unique_groups_count=8,
                peak_hour=14,
                peak_hour_requests=15,
                cache_hits_total=200,
                cache_misses_total=50,
            )
            mock_metrics.snapshot.return_value = mock_snapshot
            mock_metrics.get_uptime.return_value = __import__("datetime").timedelta(hours=2, minutes=30)

            ok = await admin_agent.handle(mock_event, "/admin stats", mock_line_bot_api)
            assert ok is True
            mock_line_bot_api.reply_message.assert_called_once()

            # The stats command may return FlexMessage or TextMessage
            # Check that a message was sent (we don't need to check specific content)
            message = mock_line_bot_api.reply_message.call_args[0][0].messages[0]

            # Verify a valid message type was returned
            from linebot.v3.messaging import FlexMessage, TextMessage

            assert isinstance(message, (TextMessage, FlexMessage))

    @pytest.mark.asyncio
    async def test_handle_purge_command(self, admin_agent, mock_event, mock_line_bot_api):
        """Test /admin purge requests confirmation (does not purge immediately)."""
        confirm_service = AdminConfirmationService()
        confirm_service._generate_token = lambda: "tok123"  # type: ignore[method-assign]
        with (
            patch("src.agents.admin_agent.admin_confirmation_service", confirm_service),
            patch("src.agents.admin_agent.session_manager") as mock_session_mgr,
        ):
            ok = await admin_agent.handle(mock_event, "/admin purge", mock_line_bot_api)
            assert ok is True
            mock_line_bot_api.push_message.assert_called_once()
            mock_session_mgr.end_session.assert_not_called()
            assert confirm_service.count_pending() == 1

    def test_priority_higher_than_translation(self, admin_agent):
        """Test that admin agent has higher priority than translation agent."""
        # Priority 5 is higher than translation agent's priority 10
        assert admin_agent.get_priority() < 10

    @pytest.mark.asyncio
    async def test_handle_news_command(self, admin_agent, mock_event, mock_line_bot_api):
        """/admin news is deprecated and should not be supported."""
        result = await admin_agent.handle(mock_event, "/admin news", mock_line_bot_api)

        assert result is True
        mock_line_bot_api.reply_message.assert_called_once()

        call_args = mock_line_bot_api.reply_message.call_args
        message_text = call_args[0][0].messages[0].text
        assert "unknown" in message_text.lower()


@pytest.fixture
def bootstrap_admin_agent():
    """Create admin agent with bootstrap key enabled but no preconfigured admins."""
    from unittest.mock import Mock

    # Reset privilege_service for clean state
    privilege_service._reset_for_testing()
    if hasattr(rate_limiter, "reset_admin_destructive_limits_for_testing"):
        rate_limiter.reset_admin_destructive_limits_for_testing()

    with patch("src.agents.admin_agent.settings") as mock_settings:
        mock_settings.get_admin_user_ids.return_value = []
        mock_settings.admin_setup_key = "setup-secret"

        # Set privilege_service state (no env admins, bootstrap mode)
        privilege_service._env_admin_user_ids = []
        privilege_service._env_moderator_user_ids = []
        privilege_service._settings_loaded = True

        # Create mock http_client for admin agent
        mock_http_client = Mock()
        agent = AdminAgent(http_client=mock_http_client, news_api_key="test_key")
        return agent


class TestAdminBootstrap:
    @pytest.mark.asyncio
    async def test_should_handle_claim_when_bootstrap_enabled(self, bootstrap_admin_agent, mock_event):
        mock_event.source.user_id = "U0000000000000000"  # not pre-authorized
        assert await bootstrap_admin_agent.should_handle(mock_event, "/admin claim setup-secret") is True

    @pytest.mark.asyncio
    async def test_claim_grants_in_memory_admin(self, bootstrap_admin_agent, mock_event, mock_line_bot_api):
        mock_event.source.user_id = "UCLAIMME123"

        # Claim
        ok = await bootstrap_admin_agent.handle(mock_event, "/admin claim setup-secret", mock_line_bot_api)
        assert ok is True

        # After claim, user should be treated as admin (via privilege_service)
        assert privilege_service.is_claimed_admin("UCLAIMME123") is True
