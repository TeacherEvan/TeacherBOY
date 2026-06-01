"""Tests for main application."""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch, MagicMock


@pytest.fixture
def mock_settings():
    """Mock settings for testing."""
    with patch("src.main.settings") as mock:
        mock.line_channel_secret = "test_secret"
        mock.line_channel_access_token = "test_token"
        mock.debug = False
        mock.is_google_translate_configured.return_value = False
        yield mock


@pytest.fixture
def client(mock_settings):
    """Create a test client."""
    from src.main import app

    return TestClient(app)


def test_root_endpoint(client):
    """Test root endpoint."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "operational"  # Updated from "ok"
    assert "Zeus" in data["service"]


def test_health_check(client):
    """Test health check endpoint."""
    with (
        patch("src.main.startup_loader.is_ready", return_value=True),
        patch(
            "src.main.agent_router.list_agents",
            return_value=[{"name": "TranslationAgent"}],
        ),
    ):
        response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()

    assert payload["status"] == "healthy"
    assert payload["checks"] == {
        "process": "alive",
        "startup_data": "ready",
        "agents_registered": 1,
    }
    assert isinstance(payload["timestamp"], str)
    assert datetime.fromisoformat(payload["timestamp"])


def test_health_check_returns_200_while_startup_data_is_loading(client):
    """Health check should stay live while startup data is still restoring."""
    with (
        patch("src.main.startup_loader.is_ready", return_value=False),
        patch("src.main.agent_router.list_agents", return_value=[]),
    ):
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["checks"] == {
        "process": "alive",
        "startup_data": "loading",
        "agents_registered": 0,
    }


def test_health_check_does_not_call_translation_providers(client, mock_settings):
    """Health check should remain liveness-only and avoid translation probes."""
    mock_settings.is_google_translate_configured.return_value = True

    with (
        patch("src.main.startup_loader.is_ready", return_value=True),
        patch(
            "src.main.agent_router.list_agents",
            return_value=[{"name": "TranslationAgent"}],
        ),
        patch(
            "src.main.google_translation_service.translate",
            new_callable=AsyncMock,
            side_effect=AssertionError("google translate probe should not run"),
        ) as google_translate,
        patch(
            "src.main.translation_service.translate",
            new_callable=AsyncMock,
            side_effect=AssertionError("libretranslate probe should not run"),
        ) as libretranslate,
    ):
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    google_translate.assert_not_awaited()
    libretranslate.assert_not_awaited()


def test_readiness_returns_503_when_startup_data_is_not_ready(client):
    """Readiness should report loading while startup data is still restoring."""
    with (
        patch("src.main.startup_loader.is_ready", return_value=False),
        patch("src.main.agent_router.list_agents", return_value=[]),
    ):
        response = client.get("/readiness")

    assert response.status_code == 503
    assert response.json() == {
        "ready": False,
        "checks": {
            "startup_data": "loading",
            "agents_registered": 0,
        },
        "google_translate_enabled": False,
    }


def test_readiness_returns_503_when_startup_data_is_ready_but_no_agents_registered(
    client,
):
    """Readiness should stay unavailable until at least one agent is registered."""
    with (
        patch("src.main.startup_loader.is_ready", return_value=True),
        patch("src.main.agent_router.list_agents", return_value=[]),
    ):
        response = client.get("/readiness")

    assert response.status_code == 503
    assert response.json() == {
        "ready": False,
        "checks": {
            "startup_data": "ready",
            "agents_registered": 0,
        },
        "google_translate_enabled": False,
    }


def test_readiness_returns_200_when_startup_data_is_ready_and_agents_registered(client):
    """Readiness should report ready only after startup data and agents are available."""
    with (
        patch("src.main.startup_loader.is_ready", return_value=True),
        patch(
            "src.main.agent_router.list_agents",
            return_value=[
                {
                    "name": "TranslationAgent",
                    "enabled": True,
                    "priority": 10,
                    "description": "Handles translation",
                }
            ],
        ),
    ):
        response = client.get("/readiness")

    assert response.status_code == 200
    assert response.json() == {
        "ready": True,
        "checks": {
            "startup_data": "ready",
            "agents_registered": 1,
        },
        "google_translate_enabled": False,
    }


def test_webhook_invalid_signature(client):
    """Test webhook with invalid signature."""
    response = client.post(
        "/webhook",
        json={"events": []},
        headers={"X-Line-Signature": "invalid_signature"},
    )
    assert response.status_code == 400


def test_webhook_missing_signature(client):
    """Test webhook without signature header."""
    response = client.post("/webhook", json={"events": []})
    # Should return 400 for invalid signature
    assert response.status_code == 400


def test_webhook_unexpected_parser_exception_returns_generic_500(client):
    """Webhook should not leak unexpected parser exception details."""
    with patch("src.main.webhook_parser.parse", side_effect=ValueError("boom")):
        response = client.post(
            "/webhook",
            json={"events": []},
            headers={"X-Line-Signature": "valid_signature"},
        )

    assert response.status_code == 500
    assert response.json() == {
        "status": "error",
        "detail": "Internal server error",
    }


def test_webhook_invalid_utf8_body_returns_generic_500(client):
    """Webhook should return the generic JSON 500 for malformed raw bytes."""
    response = client.post(
        "/webhook",
        content=b"\xff",
        headers={
            "X-Line-Signature": "valid_signature",
            "Content-Type": "application/octet-stream",
        },
    )

    assert response.status_code == 500
    assert response.json() == {
        "status": "error",
        "detail": "Internal server error",
    }
