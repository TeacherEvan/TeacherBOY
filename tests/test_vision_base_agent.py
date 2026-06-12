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
        mock_messaging_api_blob = MagicMock(spec=MessagingApiBlob)
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
    def mock_github_service(self):
        with patch("src.services.github_models_service.github_models_service") as mock:
            yield mock

    @pytest.fixture
    def mock_openrouter_service(self):
        with patch("src.services.openrouter_service.openrouter_service") as mock:
            yield mock

    def test_get_chat_id_user(self, vision_base_agent, mock_event):
        chat_id = vision_base_agent._get_chat_id(mock_event)
        assert chat_id == "user_test_user"

    def test_get_chat_id_group(self, vision_base_agent, mock_event):
        mock_event.source.user_id = None
        mock_event.source.group_id = "test_group"
        chat_id = vision_base_agent._get_chat_id(mock_event)
        assert chat_id == "group_test_group"

    def test_get_chat_id_room(self, vision_base_agent, mock_event):
        mock_event.source.user_id = None
        mock_event.source.room_id = "test_room"
        chat_id = vision_base_agent._get_chat_id(mock_event)
        assert chat_id == "room_test_room"

    @pytest.mark.asyncio
    async def test_download_image_success(self, vision_base_agent, mock_line_api_client):
        mock_message_id = "test_message_id"
        mock_image_bytes = b"fake_image_bytes"

        mock_blob_api = vision_base_agent.blob_api
        mock_blob_api.get_message_content = AsyncMock(return_value=mock_image_bytes)

        with patch.object(settings, "line_channel_access_token", "fake_token"):
            downloaded_bytes = await vision_base_agent._download_image(mock_message_id)

        assert downloaded_bytes == mock_image_bytes
        mock_blob_api.get_message_content.assert_called_once_with(mock_message_id)

    @pytest.mark.asyncio
    async def test_download_image_failure(self, vision_base_agent, mock_line_api_client):
        mock_message_id = "test_message_id"

        mock_blob_api = vision_base_agent.blob_api
        mock_blob_api.get_message_content = AsyncMock(side_effect=Exception("Download error"))

        with patch.object(settings, "line_channel_access_token", "fake_token"):
            downloaded_bytes = await vision_base_agent._download_image(mock_message_id)

        assert downloaded_bytes is None
        mock_blob_api.get_message_content.assert_called_once_with(mock_message_id)

    def test_build_vision_message_standard(self, vision_base_agent):
        image_data_url = "data:image/jpeg;base64,abc"
        question = "What is this image about?"
        messages = vision_base_agent._build_vision_message(image_data_url, question, scene_mode="standard")

        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert "Examine this image and answer my question" in messages[1]["content"][0]["text"]
        assert messages[1]["content"][1]["image_url"]["url"] == image_data_url

    def test_build_vision_message_literal_scene(self, vision_base_agent):
        image_data_url = "data:image/jpeg;base64,abc"
        question = "Tell me about the baby"
        messages = vision_base_agent._build_vision_message(image_data_url, question, scene_mode="literal")

        assert "Stay extremely literal and calm" in messages[0]["content"]

    def test_get_vision_error_detail(self, vision_base_agent, mock_github_service, mock_openrouter_service):
        mock_github_service.get_last_error.return_value = (400, "Bad Request", "github_model")
        mock_openrouter_service.get_last_error.return_value = None

        status, detail, model = vision_base_agent._get_vision_error_detail()
        assert status == 400
        assert detail == "Bad Request"
        assert model == "github_model"

        mock_github_service.get_last_error.return_value = None
        mock_openrouter_service.get_last_error.return_value = (401, "Unauthorized", "openrouter_model")
        status, detail, model = vision_base_agent._get_vision_error_detail()
        assert status == 401
        assert detail == "Unauthorized"
        assert model == "openrouter_model"

        mock_github_service.get_last_error.return_value = None
        mock_openrouter_service.get_last_error.return_value = None
        status, detail, model = vision_base_agent._get_vision_error_detail()
        assert status is None
        assert detail is None
        assert model is None
