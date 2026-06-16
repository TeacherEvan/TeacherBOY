from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from linebot.v3.messaging import MessagingApiBlob
from linebot.v3.webhooks import MessageEvent, Source

from src.agents.vision_base_agent import VisionBaseAgent
from src.config import settings


class TestVisionBaseAgent:
    @pytest.fixture
    def mock_line_api_client(self):
        with patch("linebot.v3.messaging.ApiClient") as mock_api_client_class:
            mock_api_client = MagicMock()
            mock_api_client_class.return_value.__enter__.return_value = mock_api_client
            yield mock_api_client

    @pytest.fixture
    def vision_base_agent(self, mock_line_api_client):
        mock_messaging_api_blob = AsyncMock(spec=MessagingApiBlob)
        return VisionBaseAgent(
            name="VisionBaseAgent",
            description="Base agent for vision-related functionalities",
            messaging_api_blob=mock_messaging_api_blob,
        )

    @pytest.fixture
    def mock_event(self):
        event = MagicMock(spec=MessageEvent)
        event.source = MagicMock(spec=Source)
        event.source.user_id = "test_user"
        event.source.group_id = None
        event.source.room_id = None
        return event

    @pytest.fixture
    def mock_hermes_service(self):
        with patch("src.services.hermes_service.hermes_service") as mock:
            yield mock

    @pytest.fixture
    def mock_openrouter_service(self):
        with patch("src.services.openrouter_service.openrouter_service") as mock:
            yield mock

    def test_get_chat_id_user(self, vision_base_agent, mock_event):
        chat_id = vision_base_agent._get_chat_id(mock_event)
        assert chat_id == "user_test_user"

    def test_get_chat_id_group(self, vision_base_agent, mock_event):
        mock_event.source.group_id = "group123"
        chat_id = vision_base_agent._get_chat_id(mock_event)
        assert chat_id == "group_group123"

    def test_get_chat_id_room(self, vision_base_agent, mock_event):
        mock_event.source.room_id = "room123"
        chat_id = vision_base_agent._get_chat_id(mock_event)
        assert chat_id == "room_room123"

    @pytest.mark.asyncio
    async def test_download_image_success(self, vision_base_agent):
        mock_content = b"fake image data"
        vision_base_agent.blob_api.get_message_content = AsyncMock(return_value=mock_content)

        result = await vision_base_agent._download_image("test_msg_id")

        assert result == mock_content
        vision_base_agent.blob_api.get_message_content.assert_called_once_with("test_msg_id")

    @pytest.mark.asyncio
    async def test_download_image_failure(self, vision_base_agent):
        vision_base_agent.blob_api.get_message_content = AsyncMock(side_effect=Exception("Network error"))

        result = await vision_base_agent._download_image("test_msg_id")

        assert result is None

    def test_build_vision_message_standard(self, vision_base_agent):
        image_data_url = "data:image/jpeg;base64,abc"
        question = "What is this?"
        messages = vision_base_agent._build_vision_message(image_data_url, question)

        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert "Examine this image and answer my question" in messages[1]["content"][0]["text"]
        assert messages[1]["content"][1]["image_url"]["url"] == image_data_url

    def test_build_vision_message_literal_scene(self, vision_base_agent):
        image_data_url = "data:image/jpeg;base64,abc"
        question = "Tell me about the baby"
        messages = vision_base_agent._build_vision_message(image_data_url, question, scene_mode="literal")

        assert "Stay extremely literal and calm" in messages[0]["content"]

    def test_get_vision_error_detail(self, vision_base_agent, mock_openrouter_service):
        """Test that error detail can be retrieved from services."""
        # The _get_vision_error_detail method dynamically imports openrouter_service
        mock_openrouter_service.get_last_error.return_value = (400, "Bad Request", "openrouter_model")
        
        status, detail, model = vision_base_agent._get_vision_error_detail()
        assert status == 400
        assert detail == "Bad Request"
        assert model == "openrouter_model"

    def test_get_vision_error_detail_none(self, vision_base_agent, mock_openrouter_service):
        """Test when no error is available."""
        mock_openrouter_service.get_last_error.return_value = None
        
        status, detail, model = vision_base_agent._get_vision_error_detail()
        assert status is None
        assert detail is None
        assert model is None

    def test_get_vision_error_detail_services_unavailable(self, vision_base_agent):
        """Test when services module import fails."""
        with patch("src.services.openrouter_service.openrouter_service", None):
            status, detail, model = vision_base_agent._get_vision_error_detail()
            assert status is None
            assert detail is None
            assert model is None