"""Tests for admin agent functionality."""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from src.agents.admin_agent import AdminAgent
from src.services.session_manager import SessionManager
from src.services.admin_confirmation_service import AdminConfirmationService
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from linebot.v3.messaging import MessagingApi


@pytest.fixture
def admin_agent():
    """Create admin agent with test configuration."""
    from unittest.mock import Mock

    with patch("src.agents.admin_agent.settings") as mock_settings:
        mock_settings.get_admin_user_ids.return_value = [
            "U1234567890abcdef",
            "U9876543210fedcba",
        ]
        # Create mock http_client for admin agent
        mock_http_client = Mock()
        agent = AdminAgent(http_client=mock_http_client, news_api_key="test_key")
        return agent


@pytest.fixture
def mock_event():
    """Create a mock message event."""
    event = Mock(spec=MessageEvent)
    event.source = Mock()
    event.source.user_id = "U1234567890abcdef"  # Authorized admin
    event.source.group_id = None
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
        assert admin_agent._is_admin_command("Dear Zeus admin help") is True
        assert admin_agent._is_admin_command("dear zeus admin status") is True

    def test_is_admin_command_invalid(self, admin_agent):
        """Test admin command detection with invalid commands."""
        assert admin_agent._is_admin_command("admin help") is False
        assert admin_agent._is_admin_command("hello") is False
        assert admin_agent._is_admin_command("/not_admin") is False
        assert admin_agent._is_admin_command("RandomWord help") is False

    @pytest.mark.asyncio
    async def test_should_handle_authorized_admin_command(
        self, admin_agent, mock_event
    ):
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
    async def test_should_handle_non_admin_command(self, admin_agent, mock_event):
        """Test that non-admin commands are not handled."""
        result = await admin_agent.should_handle(mock_event, "hello world")
        assert result is False

    @pytest.mark.asyncio
    async def test_handle_help_command(
        self, admin_agent, mock_event, mock_line_bot_api
    ):
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

    @pytest.mark.asyncio
    async def test_handle_status_command(
        self, admin_agent, mock_event, mock_line_bot_api
    ):
        """Test /admin status command."""
        with patch("src.agents.admin_agent.session_manager") as mock_session_mgr:
            mock_session_mgr.is_session_active.return_value = False
            mock_session_mgr.is_sleeping.return_value = False
            mock_session_mgr.get_sleep_remaining.return_value = 0
            mock_session_mgr.get_session_info.return_value = {}

            result = await admin_agent.handle(
                mock_event, "/admin status", mock_line_bot_api
            )

            assert result is True
            mock_line_bot_api.reply_message.assert_called_once()

            # Check response contains status information
            call_args = mock_line_bot_api.reply_message.call_args
            message_text = call_args[0][0].messages[0].text
            assert "Status" in message_text
            assert "Chat ID" in message_text

    @pytest.mark.asyncio
    async def test_handle_wake_command(
        self, admin_agent, mock_event, mock_line_bot_api
    ):
        """Test /admin wake command."""
        with patch("src.agents.admin_agent.session_manager") as mock_session_mgr:
            mock_session_mgr.is_sleeping.return_value = True
            mock_session_mgr.wake_chat.return_value = True

            result = await admin_agent.handle(
                mock_event, "/admin wake", mock_line_bot_api
            )

            assert result is True
            mock_session_mgr.wake_chat.assert_called_once()
            mock_line_bot_api.reply_message.assert_called_once()

            call_args = mock_line_bot_api.reply_message.call_args
            message_text = call_args[0][0].messages[0].text
            assert "woken" in message_text.lower() or "wake" in message_text.lower()

    @pytest.mark.asyncio
    async def test_handle_sleep_command(
        self, admin_agent, mock_event, mock_line_bot_api
    ):
        """Test /admin sleep command."""
        with patch("src.agents.admin_agent.session_manager") as mock_session_mgr:
            result = await admin_agent.handle(
                mock_event, "/admin sleep 12", mock_line_bot_api
            )

            assert result is True
            # Check that sleep_chat was called with correct hours
            mock_session_mgr.sleep_chat.assert_called_once()
            call_args = mock_session_mgr.sleep_chat.call_args
            # Should be called with chat_id and hours
            assert call_args[0][1] == 12 or call_args[1].get("hours") == 12

    @pytest.mark.asyncio
    async def test_handle_reset_command(
        self, admin_agent, mock_event, mock_line_bot_api
    ):
        """Test /admin reset command."""
        with patch("src.agents.admin_agent.session_manager") as mock_session_mgr:
            mock_session_mgr.end_session.return_value = True
            mock_session_mgr.wake_chat.return_value = False

            result = await admin_agent.handle(
                mock_event, "/admin reset", mock_line_bot_api
            )

            assert result is True
            mock_session_mgr.end_session.assert_called_once()
            mock_session_mgr.clear_message_history.assert_called_once()
            mock_session_mgr.wake_chat.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_sessions_command(
        self, admin_agent, mock_event, mock_line_bot_api
    ):
        """Test /admin sessions command."""
        with patch("src.agents.admin_agent.session_manager") as mock_session_mgr:
            # Mock active sessions using public method
            mock_session_mgr.get_active_sessions.return_value = {
                "user_U123": {"user_id": "U123", "message_count": 5}
            }
            mock_session_mgr.get_sleeping_chats.return_value = {}

            result = await admin_agent.handle(
                mock_event, "/admin sessions", mock_line_bot_api
            )

            assert result is True
            mock_line_bot_api.reply_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_unknown_command(
        self, admin_agent, mock_event, mock_line_bot_api
    ):
        """Test handling of unknown admin command."""
        result = await admin_agent.handle(
            mock_event, "/admin unknown_cmd", mock_line_bot_api
        )

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
    async def test_handle_leave_current_group(
        self, admin_agent, mock_event, mock_line_bot_api
    ):
        """Test /admin leave requests confirmation (does not leave immediately)."""
        mock_event.source.group_id = "C123456"
        mock_event.source.room_id = None

        confirm_service = AdminConfirmationService()
        confirm_service._generate_token = lambda: "tok123"  # type: ignore[method-assign]
        with patch(
            "src.agents.admin_agent.admin_confirmation_service", confirm_service
        ):
            ok = await admin_agent.handle(mock_event, "/admin leave", mock_line_bot_api)
        assert ok is True
        mock_line_bot_api.reply_message.assert_called_once()
        mock_line_bot_api.push_message.assert_called_once()
        mock_line_bot_api.leave_group.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_leave_specific_group_chat_id(
        self, admin_agent, mock_event, mock_line_bot_api
    ):
        """Test /admin leave group_<id> requests confirmation."""
        # Simulate running the command from anywhere
        mock_event.source.group_id = None
        mock_event.source.room_id = None

        confirm_service = AdminConfirmationService()
        confirm_service._generate_token = lambda: "tok123"  # type: ignore[method-assign]
        with patch(
            "src.agents.admin_agent.admin_confirmation_service", confirm_service
        ):
            ok = await admin_agent.handle(
                mock_event, "/admin leave group_C999", mock_line_bot_api
            )
        assert ok is True
        mock_line_bot_api.reply_message.assert_called_once()
        mock_line_bot_api.push_message.assert_called_once()
        mock_line_bot_api.leave_group.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_leave_invalid_in_user_chat(
        self, admin_agent, mock_event, mock_line_bot_api
    ):
        """Test /admin leave errors in 1:1 chat without a target."""
        mock_event.source.group_id = None
        mock_event.source.room_id = None

        ok = await admin_agent.handle(mock_event, "/admin leave", mock_line_bot_api)
        assert ok is True
        mock_line_bot_api.reply_message.assert_called_once()
        mock_line_bot_api.leave_group.assert_not_called()
        mock_line_bot_api.leave_room.assert_not_called()

    @pytest.mark.asyncio
    async def test_confirm_executes_leave_in_private_chat(
        self, admin_agent, mock_event, mock_line_bot_api
    ):
        """Test /admin confirm executes the pending leave action when run in private chat."""
        confirm_service = AdminConfirmationService()
        confirm_service._generate_token = lambda: "tok123"  # type: ignore[method-assign]

        # Request leave for a specific group
        mock_event.source.group_id = None
        mock_event.source.room_id = None
        with patch(
            "src.agents.admin_agent.admin_confirmation_service", confirm_service
        ):
            ok = await admin_agent.handle(
                mock_event, "/admin leave group_C999", mock_line_bot_api
            )
            assert ok is True

            # Confirm in private chat (user_*)
            confirm_event = Mock(spec=MessageEvent)
            confirm_event.source = Mock()
            confirm_event.source.user_id = mock_event.source.user_id
            confirm_event.source.group_id = None
            confirm_event.source.room_id = None
            confirm_event.reply_token = "confirm_reply_token"

            ok2 = await admin_agent.handle(
                confirm_event, "/admin confirm tok123", mock_line_bot_api
            )
            assert ok2 is True
            mock_line_bot_api.leave_group.assert_called_once_with("C999")

    @pytest.mark.asyncio
    async def test_stats_command(self, admin_agent, mock_event, mock_line_bot_api):
        """Test /admin stats returns enhanced dashboard response."""
        with patch("src.agents.admin_agent.session_manager") as mock_session_mgr, patch(
            "src.agents.admin_agent.metrics_service"
        ) as mock_metrics:
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
            mock_metrics.get_uptime.return_value = __import__("datetime").timedelta(
                hours=2, minutes=30
            )

            ok = await admin_agent.handle(mock_event, "/admin stats", mock_line_bot_api)
            assert ok is True
            mock_line_bot_api.reply_message.assert_called_once()
            msg_text = mock_line_bot_api.reply_message.call_args[0][0].messages[0].text

            # Verify enhanced stats sections are present
            assert "Admin Stats Dashboard" in msg_text
            assert "SYSTEM STATUS" in msg_text
            assert "USAGE METRICS" in msg_text
            assert "USER ENGAGEMENT" in msg_text
            assert "ACTIVE SESSIONS" in msg_text
            assert "CACHE PERFORMANCE" in msg_text

            # Verify key metrics are displayed
            assert "Translations: 100" in msg_text
            assert "Google: 80, Libre: 20" in msg_text
            assert "News requests: 50" in msg_text
            assert "Admin commands: 10" in msg_text
            assert "Failed translations: 3" in msg_text
            assert "Rate limited: 5" in msg_text
            assert "Unique users: 25" in msg_text
            assert "Unique groups: 8" in msg_text
            assert "Peak hour: 14:00 UTC (15 req)" in msg_text
            assert "Hit rate:" in msg_text

    @pytest.mark.asyncio
    async def test_handle_purge_command(
        self, admin_agent, mock_event, mock_line_bot_api
    ):
        """Test /admin purge requests confirmation (does not purge immediately)."""
        confirm_service = AdminConfirmationService()
        confirm_service._generate_token = lambda: "tok123"  # type: ignore[method-assign]
        with patch(
            "src.agents.admin_agent.admin_confirmation_service", confirm_service
        ), patch("src.agents.admin_agent.session_manager") as mock_session_mgr, patch(
            "src.agents.admin_agent.rate_limiter"
        ) as mock_rate_limiter:
            ok = await admin_agent.handle(mock_event, "/admin purge", mock_line_bot_api)
            assert ok is True
            mock_line_bot_api.push_message.assert_called_once()
            mock_session_mgr.end_session.assert_not_called()
            mock_rate_limiter.reset_chat.assert_not_called()

    def test_priority_higher_than_translation(self, admin_agent):
        """Test that admin agent has higher priority than translation agent."""
        # Priority 5 is higher than translation agent's priority 10
        assert admin_agent.get_priority() < 10

    @pytest.mark.asyncio
    async def test_handle_news_command(
        self, admin_agent, mock_event, mock_line_bot_api
    ):
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

    with patch("src.agents.admin_agent.settings") as mock_settings:
        mock_settings.get_admin_user_ids.return_value = []
        mock_settings.admin_setup_key = "setup-secret"
        # Create mock http_client for admin agent
        mock_http_client = Mock()
        agent = AdminAgent(http_client=mock_http_client, news_api_key="test_key")
        return agent


class TestAdminBootstrap:
    @pytest.mark.asyncio
    async def test_should_handle_claim_when_bootstrap_enabled(
        self, bootstrap_admin_agent, mock_event
    ):
        mock_event.source.user_id = "U0000000000000000"  # not pre-authorized
        assert (
            await bootstrap_admin_agent.should_handle(
                mock_event, "/admin claim setup-secret"
            )
            is True
        )

    @pytest.mark.asyncio
    async def test_claim_grants_in_memory_admin(
        self, bootstrap_admin_agent, mock_event, mock_line_bot_api
    ):
        mock_event.source.user_id = "UCLAIMME123"

        # Claim
        ok = await bootstrap_admin_agent.handle(
            mock_event, "/admin claim setup-secret", mock_line_bot_api
        )
        assert ok is True

        # After claim, user should be treated as admin
        assert bootstrap_admin_agent._is_admin("UCLAIMME123") is True
