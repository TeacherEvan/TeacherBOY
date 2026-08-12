"""Tests for ProfilerAgent - Psychological profiling from photos."""

import base64
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_settings():
    """Mock settings for profiler tests."""
    mock = MagicMock()
    mock.profiler_enabled = True
    mock.profiler_model = "openai/gpt-4o"
    mock.profiler_analysis_type = "full"
    mock.profiler_rate_limit_per_hour = 3
    mock.profiler_max_image_size_mb = 10.0
    mock.line_channel_access_token = "test_token"
    mock.get_admin_user_ids.return_value = ["admin123"]
    mock.is_profiler_configured.return_value = True
    return mock


@pytest.fixture
def mock_event():
    """Create mock LINE MessageEvent with image message."""
    event = MagicMock()
    event.message = MagicMock()
    event.message.type = "image"
    event.message.id = "test_message_id_123"
    event.source = MagicMock()
    event.source.user_id = "user123"
    event.source.group_id = None
    event.source.room_id = None
    event.reply_token = "test_reply_token"
    return event


@pytest.fixture
def mock_text_event():
    """Create mock LINE MessageEvent with text message."""
    event = MagicMock()
    event.message = MagicMock()
    event.message.type = "text"
    event.message.text = "hello"
    event.source = MagicMock()
    event.source.user_id = "user123"
    event.source.group_id = None
    event.source.room_id = None
    event.reply_token = "test_reply_token"
    return event


@pytest.fixture
def mock_line_api():
    """Create mock LINE MessagingApi."""
    api = MagicMock()
    api.reply_message = MagicMock()
    api.push_message = MagicMock()
    return api


class TestProfilerAgentShouldHandle:
    """Tests for ProfilerAgent.should_handle()."""

    @pytest.mark.asyncio
    async def test_should_handle_text_trigger(self, mock_text_event, mock_settings):
        """Test that profiler handles text messages with trigger phrases.

        Note: Profiler uses FACE-SPECIFIC triggers only.
        "analyze" keywords go to ImageAnalyzerAgent for general image Q&A.
        """
        with (
            patch("src.agents.profiler_agent.settings", mock_settings),
            patch("src.agents.profiler_agent.hermes_service") as mock_hermes,
            patch("src.agents.profiler_agent.openrouter_service") as mock_openrouter,
        ):
            mock_hermes.is_vision_configured.return_value = True
            mock_openrouter.is_configured.return_value = True

            from src.agents.profiler_agent import ProfilerAgent

            agent = ProfilerAgent()

            # Test face-specific trigger phrases (no "analyze" - that goes to ImageAnalyzer)
            triggers = [
                "Ms. Green profile",
                "profile this",
                "profile image",
                "profile photo",
                "profile face",
                "profile person",
                "Ms. Green read face",
                "read this face",
                "read face",
                "Ms. Green face",
                "face analysis",
                "facial analysis",
                "read expression",
                "read emotions",
            ]

            for trigger in triggers:
                mock_text_event.message.text = trigger
                result = await agent.should_handle(mock_text_event, trigger)
                assert result is True, f"Trigger '{trigger}' should be handled"

    @pytest.mark.asyncio
    async def test_should_not_handle_analyze_triggers(self, mock_text_event, mock_settings):
        """Test that profiler does NOT handle 'analyze' triggers (those go to ImageAnalyzer)."""
        with (
            patch("src.agents.profiler_agent.settings", mock_settings),
            patch("src.agents.profiler_agent.hermes_service") as mock_hermes,
            patch("src.agents.profiler_agent.openrouter_service") as mock_openrouter,
        ):
            mock_hermes.is_vision_configured.return_value = True
            mock_openrouter.is_configured.return_value = True

            from src.agents.profiler_agent import ProfilerAgent

            agent = ProfilerAgent()

            # These should NOT trigger Profiler - they go to ImageAnalyzer
            analyze_triggers = [
                "analyze this image",
                "analyze this photo",
                "analyze image",
                "analyze photo",
                "zeus analyze",
                "zeus analyze this",
            ]

            for trigger in analyze_triggers:
                mock_text_event.message.text = trigger
                result = await agent.should_handle(mock_text_event, trigger)
                assert result is False, f"Trigger '{trigger}' should NOT be handled by Profiler"

    @pytest.mark.asyncio
    async def test_should_not_handle_legacy_zeus_profile_trigger(self, mock_text_event, mock_settings):
        with (
            patch("src.agents.profiler_agent.settings", mock_settings),
            patch("src.agents.profiler_agent.hermes_service") as mock_hermes,
            patch("src.agents.profiler_agent.openrouter_service") as mock_openrouter,
        ):
            mock_hermes.is_vision_configured.return_value = True
            mock_openrouter.is_configured.return_value = True

            from src.agents.profiler_agent import ProfilerAgent

            agent = ProfilerAgent()

            result = await agent.should_handle(mock_text_event, "zeus profile")
            assert result is False

    @pytest.mark.asyncio
    async def test_should_handle_image_with_active_session(self, mock_event, mock_settings):
        """Test that profiler handles image when session is active."""
        with (
            patch("src.agents.profiler_agent.settings", mock_settings),
            patch("src.agents.profiler_agent.hermes_service") as mock_hermes,
            patch("src.agents.profiler_agent.openrouter_service") as mock_openrouter,
            patch("src.agents.profiler_agent.profiler_session_manager") as mock_session,
        ):
            mock_hermes.is_vision_configured.return_value = True
            mock_openrouter.is_configured.return_value = True
            mock_session.is_waiting_for_image.return_value = True  # Active session

            from src.agents.profiler_agent import ProfilerAgent

            agent = ProfilerAgent()

            result = await agent.should_handle(mock_event, "")
            assert result is True

    @pytest.mark.asyncio
    async def test_should_not_handle_image_without_session(self, mock_event, mock_settings):
        """Test that profiler rejects image without active session (no trigger sent)."""
        with (
            patch("src.agents.profiler_agent.settings", mock_settings),
            patch("src.agents.profiler_agent.hermes_service") as mock_hermes,
            patch("src.agents.profiler_agent.openrouter_service") as mock_openrouter,
            patch("src.agents.profiler_agent.profiler_session_manager") as mock_session,
        ):
            mock_hermes.is_vision_configured.return_value = True
            mock_openrouter.is_configured.return_value = True
            mock_session.is_waiting_for_image.return_value = False  # No session

            from src.agents.profiler_agent import ProfilerAgent

            agent = ProfilerAgent()

            result = await agent.should_handle(mock_event, "")
            assert result is False  # Should reject images without trigger

    @pytest.mark.asyncio
    async def test_should_not_handle_text_without_trigger(self, mock_text_event, mock_settings):
        """Test that profiler does NOT handle text messages without triggers."""
        with (
            patch("src.agents.profiler_agent.settings", mock_settings),
            patch("src.agents.profiler_agent.hermes_service") as mock_hermes,
            patch("src.agents.profiler_agent.openrouter_service") as mock_openrouter,
        ):
            mock_hermes.is_vision_configured.return_value = True
            mock_openrouter.is_configured.return_value = True

            from src.agents.profiler_agent import ProfilerAgent

            agent = ProfilerAgent()

            result = await agent.should_handle(mock_text_event, "hello")
            assert result is False

    @pytest.mark.asyncio
    async def test_should_not_handle_when_disabled(self, mock_event):
        """Test that profiler doesn't handle when disabled."""
        mock_settings = MagicMock()
        mock_settings.profiler_enabled = False
        mock_settings.get_admin_user_ids.return_value = []

        with patch("src.agents.profiler_agent.settings", mock_settings):
            from src.agents.profiler_agent import ProfilerAgent

            agent = ProfilerAgent()

            result = await agent.should_handle(mock_event, "")
            assert result is False

    @pytest.mark.asyncio
    async def test_should_not_handle_when_github_not_configured(self, mock_event, mock_settings):
        """Test that profiler doesn't handle when no vision providers configured."""
        with (
            patch("src.agents.profiler_agent.settings", mock_settings),
            patch("src.agents.profiler_agent.hermes_service") as mock_hermes,
            patch("src.agents.profiler_agent.openrouter_service") as mock_openrouter,
        ):
            mock_hermes.is_vision_configured.return_value = False
            mock_openrouter.is_configured.return_value = False

            from src.agents.profiler_agent import ProfilerAgent

            agent = ProfilerAgent()

            result = await agent.should_handle(mock_event, "")
            assert result is False

    @pytest.mark.asyncio
    async def test_handle_routes_consented_ai_generated_trigger_to_literal_mode(
        self, mock_text_event, mock_line_api, mock_settings
    ):
        """AI-generated content declared by a consented owner should use literal mode immediately."""
        mock_text_event.message.text = "Ms. Green profile this AI-generated image"
        mock_text_event.source.user_id = "admin123"

        with (
            patch("src.agents.profiler_agent.settings", mock_settings),
            patch("src.agents.profiler_agent.hermes_service") as mock_hermes,
            patch("src.agents.profiler_agent.openrouter_service") as mock_openrouter,
            patch("src.agents.profiler_agent.image_consent_service") as mock_consent,
            patch("src.agents.profiler_agent.profiler_session_manager") as mock_session,
            patch("src.agents.profiler_agent.asyncio.to_thread"),
        ):
            mock_hermes.is_vision_configured.return_value = True
            mock_openrouter.is_configured.return_value = True
            mock_consent.should_use_literal_mode.return_value = True

            from src.agents.profiler_agent import ProfilerAgent

            agent = ProfilerAgent()
            agent._download_image = AsyncMock(return_value=b"image-bytes")
            agent._send_analyzing_message = AsyncMock()
            agent._send_error_message = AsyncMock()

            await agent.handle(mock_text_event, mock_text_event.message.text, mock_line_api)

            mock_consent.should_use_literal_mode.assert_called_once_with("admin123", True)
            mock_session.request_profiling.assert_called_once()
            assert mock_session.request_profiling.call_args.kwargs.get("analysis_mode") == "literal"


class TestProfilerAgentPriority:
    """Tests for ProfilerAgent priority."""

    def test_priority_is_7(self, mock_settings):
        """Test that profiler has priority 7."""
        with patch("src.agents.profiler_agent.settings", mock_settings):
            from src.agents.profiler_agent import ProfilerAgent

            agent = ProfilerAgent()

            assert agent.get_priority() == 7

    def test_priority_after_admin_before_search(self, mock_settings):
        """Test that profiler priority is between admin and search agents."""
        with patch("src.agents.profiler_agent.settings", mock_settings):
            from src.agents.profiler_agent import ProfilerAgent

            agent = ProfilerAgent()
            priority = agent.get_priority()

            # Admin is 5, Search is 8
            assert priority > 5  # After admin
            assert priority < 8  # Before search


class TestProfilerAgentHandle:
    """Tests for ProfilerAgent.handle()."""

    @pytest.mark.asyncio
    async def test_handle_trigger_sets_session(self, mock_text_event, mock_line_api, mock_settings):
        """Test that trigger phrase sets profiling session."""
        mock_text_event.message.text = "zeus profile"

        with (
            patch("src.agents.profiler_agent.settings", mock_settings),
            patch("src.agents.profiler_agent.hermes_service") as mock_hermes,
            patch("src.agents.profiler_agent.openrouter_service") as mock_openrouter,
            patch("src.agents.profiler_agent.profiler_session_manager") as mock_session,
            patch("src.agents.profiler_agent.asyncio.to_thread") as mock_thread,
        ):
            mock_hermes.is_vision_configured.return_value = True
            mock_openrouter.is_configured.return_value = True

            from src.agents.profiler_agent import ProfilerAgent

            agent = ProfilerAgent()

            result = await agent.handle(mock_text_event, "zeus profile", mock_line_api)

            assert result is True
            # Verify session was created
            mock_session.request_profiling.assert_called_once()
            # Verify confirmation message sent
            mock_thread.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_image_rate_limited(self, mock_event, mock_line_api, mock_settings):
        """Test rate limiting for non-admin users when analyzing image."""
        with (
            patch("src.agents.profiler_agent.settings", mock_settings),
            patch("src.agents.profiler_agent.hermes_service") as mock_hermes,
            patch("src.agents.profiler_agent.openrouter_service") as mock_openrouter,
            patch("src.agents.profiler_agent.profiler_rate_limiter") as mock_limiter,
            patch("src.agents.profiler_agent.metrics_service"),
            patch("src.agents.profiler_agent.profiler_session_manager") as mock_session,
        ):
            mock_hermes.is_vision_configured.return_value = True
            mock_openrouter.is_configured.return_value = True
            mock_limiter.is_allowed.return_value = False
            mock_limiter.get_reset_time.return_value = 3600
            mock_session.is_waiting_for_image.return_value = True  # Active session

            from src.agents.profiler_agent import ProfilerAgent

            agent = ProfilerAgent()

            result = await agent.handle(mock_event, "", mock_line_api)

            assert result is True  # Handled (with rate limit message)
            mock_limiter.is_allowed.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_image_admin_bypasses_rate_limit(self, mock_event, mock_line_api, mock_settings):
        """Test that admin users bypass rate limiting when analyzing image."""
        mock_event.source.user_id = "admin123"  # Admin user

        with (
            patch("src.agents.profiler_agent.settings", mock_settings),
            patch("src.agents.profiler_agent.hermes_service") as mock_hermes,
            patch("src.agents.profiler_agent.openrouter_service") as mock_openrouter,
            patch("src.agents.profiler_agent.profiler_rate_limiter") as mock_limiter,
            patch("src.agents.profiler_agent.profiler_service"),
            patch("src.agents.profiler_agent.privilege_service") as mock_priv,
            patch("src.agents.profiler_agent.profiler_session_manager") as mock_session,
        ):
            mock_hermes.is_vision_configured.return_value = True
            mock_openrouter.is_configured.return_value = True
            mock_priv.is_claimed_admin.return_value = False  # Not runtime admin
            mock_session.is_waiting_for_image.return_value = True  # Active session

            # Simulate failed image download to exit early after admin check
            from src.agents.profiler_agent import ProfilerAgent

            agent = ProfilerAgent()
            agent._download_image = AsyncMock(return_value=None)
            agent._send_analyzing_message = AsyncMock()
            agent._send_error_message = AsyncMock()

            await agent.handle(mock_event, "", mock_line_api)

            # Rate limiter should NOT be called for admins
            mock_limiter.is_allowed.assert_not_called()


class TestProfilerAgentImageDownload:
    """Tests for image download functionality."""

    @pytest.mark.asyncio
    async def test_download_image_stub(self, mock_settings):
        """Placeholder test for image download - requires LINE SDK mocking."""
        # This test requires complex LINE SDK mocking
        # The actual _download_image method uses LINE SDK which is hard to mock
        # Simply verify the method exists
        with patch("src.agents.profiler_agent.settings", mock_settings):
            from src.agents.profiler_agent import ProfilerAgent

            agent = ProfilerAgent()

            assert hasattr(agent, "_download_image")
            assert callable(agent._download_image)


class TestProfilerService:
    """Tests for profiler_service functionality."""

    def test_get_profiling_prompt_full(self):
        """Test full profiling prompt generation."""
        from src.services.profiler_service import profiler_service

        prompt = profiler_service.get_profiling_prompt()

        assert "FBI" in prompt
        assert "Ekman" in prompt or "FACS" in prompt
        assert "body language" in prompt.lower() or "Navarro" in prompt
        assert len(prompt) > 500  # Should be comprehensive

    def test_get_quick_analysis_prompt(self):
        """Test quick analysis prompt generation."""
        from src.services.profiler_service import profiler_service

        prompt = profiler_service.get_quick_analysis_prompt()

        assert len(prompt) > 100  # Should have content
        assert "emotion" in prompt.lower()  # Quick mode focuses on emotions

    def test_encode_image_to_base64(self):
        """Test base64 encoding of image bytes."""
        from src.services.profiler_service import profiler_service

        test_bytes = b"test image data"
        encoded = profiler_service.encode_image_to_base64(test_bytes)

        # Should be valid base64
        decoded = base64.b64decode(encoded)
        assert decoded == test_bytes

    def test_get_image_data_url(self):
        """Test data URL generation for images."""
        from src.services.profiler_service import profiler_service

        test_bytes = b"test image data"
        data_url = profiler_service.get_image_data_url(test_bytes)

        assert data_url.startswith("data:image/jpeg;base64,")
        # Extract and decode the base64 part
        base64_part = data_url.split(",")[1]
        decoded = base64.b64decode(base64_part)
        assert decoded == test_bytes

    def test_build_vision_message(self):
        """Test vision message building for API."""
        from src.services.profiler_service import profiler_service

        test_data_url = "data:image/jpeg;base64,dGVzdA=="
        messages = profiler_service.build_vision_message(test_data_url, "full")

        assert len(messages) >= 1
        # Should have user message with content array
        user_msg = messages[-1]
        assert user_msg["role"] == "user"
        assert isinstance(user_msg["content"], list)

        # Should have text and image_url content
        content_types = [item["type"] for item in user_msg["content"]]
        assert "text" in content_types
        assert "image_url" in content_types

    def test_format_response_for_line(self):
        """Test LINE message formatting."""
        from src.services.profiler_service import profiler_service

        test_analysis = "This is a test analysis that is quite long. " * 50
        formatted = profiler_service.format_response_for_line(test_analysis)

        # Should respect LINE character limit
        assert len(formatted) <= 5000

        # Should include a visible branded header
        assert "🔬" in formatted or "MS. GREEN" in formatted.upper()

    def test_format_response_short_text(self):
        """Test LINE formatting with short text."""
        from src.services.profiler_service import profiler_service

        test_analysis = "Short analysis."
        formatted = profiler_service.format_response_for_line(test_analysis)

        # Should include disclaimer footer
        assert "educational" in formatted.lower() or "entertainment" in formatted.lower()


class TestProfilerConfig:
    """Tests for profiler configuration."""

    def test_config_has_profiler_settings(self):
        """Test that config has profiler settings."""
        from src.config import Settings

        settings = Settings()

        assert hasattr(settings, "profiler_enabled")
        assert hasattr(settings, "profiler_model")
        assert hasattr(settings, "profiler_analysis_type")
        assert hasattr(settings, "profiler_rate_limit_per_hour")

    def test_config_profiler_defaults(self):
        """Test profiler configuration defaults."""
        from src.config import Settings

        settings = Settings(_env_file=None)

        assert settings.profiler_enabled is True
        assert settings.profiler_model == "openai/gpt-4o"
        assert settings.profiler_analysis_type == "full"
        assert settings.profiler_rate_limit_per_hour == 3

    def test_is_profiler_configured(self):
        """Test is_profiler_configured helper method."""
        from src.config import Settings

        settings = Settings()

        # Should return False when GitHub Models not configured
        assert settings.is_profiler_configured() is True  # profiler_enabled is True


class TestAgentRouterImageHandling:
    """Tests for agent router handling image messages."""

    @pytest.mark.asyncio
    async def test_router_routes_image_to_profiler(self, mock_settings):
        """Test that agent router routes image messages correctly."""
        from src.agents.agent_router import AgentRouter

        router = AgentRouter()

        # Create mock profiler agent
        mock_profiler = MagicMock()
        mock_profiler.name = "ProfilerAgent"
        mock_profiler.enabled = True
        mock_profiler.get_priority.return_value = 7
        mock_profiler.should_handle = AsyncMock(return_value=True)
        mock_profiler.handle = AsyncMock(return_value=True)

        router.register_agent(mock_profiler)

        # Create image event
        event = MagicMock()
        event.message = MagicMock()
        event.message.type = "image"
        event.source = MagicMock()
        event.source.user_id = "user123"

        # Import to get the ImageMessageContent type
        from linebot.v3.webhooks import ImageMessageContent

        event.message = MagicMock(spec=ImageMessageContent)

        mock_api = MagicMock()

        result = await router.route_message(event, mock_api)

        assert result.handled is True
        assert result.agent_name == "ProfilerAgent"
        assert result.message_type == "image"
        mock_profiler.should_handle.assert_called_once()
        mock_profiler.handle.assert_called_once()
