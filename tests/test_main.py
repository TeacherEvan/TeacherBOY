"""Tests for main application."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock


@pytest.fixture
def mock_settings():
    """Mock settings for testing."""
    with patch("src.main.settings") as mock:
        mock.line_channel_secret = "test_secret"
        mock.line_channel_access_token = "test_token"
        mock.debug = False
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
    assert "Zeus" in data["service"]]


def test_health_check(client):
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


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
