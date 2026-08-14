"""Tests for the app camera receipt flow (scan_receipt_for_app + /receipt/scan route)."""

import sys
from pathlib import Path

import httpx
import pytest

# Ensure src/ is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.services.receipt_bridge import scan_receipt_for_app, ingest_receipt


class _FakeResponse:
    def __init__(self, status_code: int, json_data: dict | None = None, text: str = ""):
        self.status_code = status_code
        self._json = json_data if json_data is not None else {}
        self.text = text

    def json(self):
        return self._json


class _FakeClient:
    """Captures the POST to Convex /receipts/ingest and returns a canned response."""

    def __init__(self, response: _FakeResponse):
        self._response = response
        self.captured = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url: str, headers: dict | None = None, json: dict | None = None):
        self.captured = {"url": url, "headers": headers, "json": json}
        return self._response


@pytest.fixture
def patch_settings(monkeypatch):
    """Stub the Budget Boss Convex settings used by the bridge."""
    from unittest.mock import MagicMock

    settings = MagicMock()
    settings.budgetboss_convex_url = "https://test.convex.site"
    settings.budgetboss_sync_token = "test-sync-secret"
    settings.receipt_agent_enabled = True
    # Any other attribute access returns a harmless default.
    settings.line_channel_access_token = "test_token"
    settings.line_channel_secret = "test_secret"
    settings.log_level = "INFO"
    settings.debug = False

    import src.config as config_mod

    monkeypatch.setattr(config_mod, "settings", settings)
    return settings


@pytest.fixture
def patch_gemini(monkeypatch):
    """Stub the Gemini vision call so no network/LLM is hit."""
    import src.utils.llm_fallback as bridge

    async def fake_vision(*args, **kwargs):
        return "MERCHANT CAFE\nTOTAL 91000\nTAX 7000\n2026-08-03"

    monkeypatch.setattr(bridge, "chat_completion_with_vision_fallback", fake_vision)


async def test_scan_for_app_posts_app_prefix_and_source(
    monkeypatch, patch_settings, patch_gemini
):
    captured = {}

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, headers=None, json=None):
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return _FakeResponse(200, {"success": True, "draftId": "d1"})

    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: _Client())

    result = await scan_receipt_for_app(
        image_base64="data:image/png;base64,abc",
        convex_user_id="user_123",
        idempotency_key="key_1",
        country_hint="TH",
    )

    assert result["success"] is True
    assert captured["json"]["lineUserId"] == "app:user_123"
    assert captured["json"]["source"] == "app-camera"
    assert captured["json"]["idempotencyKey"] == "key_1"
    assert captured["headers"]["Authorization"] == "Bearer test-sync-secret"


async def test_scan_for_app_returns_404_when_user_not_found(
    monkeypatch, patch_settings, patch_gemini
):
    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, headers=None, json=None):
            return _FakeResponse(404, {"error": "User not found"})

    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: _Client())

    result = await scan_receipt_for_app(
        image_base64="data:image/png;base64,abc",
        convex_user_id="user_404",
        idempotency_key="key_2",
    )

    assert result["success"] is False
    assert result["error"] == "User not found"


async def test_scan_for_app_returns_false_when_gemini_empty(
    monkeypatch, patch_settings
):
    import src.utils.llm_fallback as llm_fallback

    async def fake_empty(*args, **kwargs):
        return None

    monkeypatch.setattr(llm_fallback, "chat_completion_with_vision_fallback", fake_empty)

    result = await scan_receipt_for_app(
        image_base64="data:image/png;base64,abc",
        convex_user_id="user_x",
        idempotency_key="key_3",
    )

    assert result["success"] is False
    assert "no text" in result["error"]


async def test_scan_for_app_returns_false_when_bridge_not_configured(
    monkeypatch, patch_gemini
):
    import src.config as config_mod

    class _Settings:
        budgetboss_convex_url = None
        budgetboss_sync_token = None
        receipt_agent_enabled = True

    monkeypatch.setattr(config_mod, "settings", _Settings())

    result = await scan_receipt_for_app(
        image_base64="data:image/png;base64,abc",
        convex_user_id="user_x",
        idempotency_key="key_4",
    )

    assert result["success"] is False
    assert result["error"] == "Bridge not configured"


# ---------------------------------------------------------------------------
# Route tests (FastAPI TestClient)
# ---------------------------------------------------------------------------

from fastapi.testclient import TestClient  # noqa: E402

import src.config as config_mod  # noqa: E402


@pytest.fixture
def client(monkeypatch):
    from unittest.mock import MagicMock

    settings = MagicMock()
    settings.budgetboss_convex_url = "https://test.convex.site"
    settings.budgetboss_sync_token = "route-secret"
    settings.receipt_agent_enabled = True
    settings.line_channel_access_token = "test_token"
    settings.line_channel_secret = "test_secret"
    settings.log_level = "INFO"
    settings.debug = False

    monkeypatch.setattr(config_mod, "settings", settings)

    # Import after settings stub so the route module reads the right value
    import importlib

    import src.main as main_mod

    importlib.reload(main_mod)

    return TestClient(main_mod.app)


def test_receipt_scan_requires_bearer_token(client):
    resp = client.post("/receipt/scan", json={"image": "x", "userId": "u", "idempotencyKey": "k"})
    assert resp.status_code == 401


def test_receipt_scan_rejects_bad_token(client):
    resp = client.post(
        "/receipt/scan",
        headers={"Authorization": "Bearer wrong"},
        json={"image": "x", "userId": "u", "idempotencyKey": "k"},
    )
    assert resp.status_code == 401


def test_receipt_scan_rejects_missing_fields(client):
    resp = client.post(
        "/receipt/scan",
        headers={"Authorization": "Bearer route-secret"},
        json={"image": "x"},
    )
    assert resp.status_code == 400


def test_receipt_scan_disabled_returns_503(client, monkeypatch):
    from unittest.mock import MagicMock

    settings = MagicMock()
    settings.budgetboss_convex_url = "https://test.convex.site"
    settings.budgetboss_sync_token = "route-secret"
    settings.receipt_agent_enabled = False
    settings.line_channel_access_token = "test_token"
    settings.line_channel_secret = "test_secret"
    settings.log_level = "INFO"
    settings.debug = False

    monkeypatch.setattr(config_mod, "settings", settings)
    import importlib

    import src.main as main_mod

    importlib.reload(main_mod)
    c = TestClient(main_mod.app)
    resp = c.post(
        "/receipt/scan",
        headers={"Authorization": "Bearer route-secret"},
        json={"image": "x", "userId": "u", "idempotencyKey": "k"},
    )
    assert resp.status_code == 503


def test_receipt_scan_success_returns_200(client, monkeypatch):
    """Full route -> bridge -> Convex POST, with Gemini stubbed."""

    async def fake_vision(*args, **kwargs):
        return "MERCHANT CAFE\nTOTAL 91000"

    import src.utils.llm_fallback as bridge

    monkeypatch.setattr(bridge, "chat_completion_with_vision_fallback", fake_vision)

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, headers=None, json=None):
            return _FakeResponse(200, {"success": True, "draftId": "draft_1"})

    monkeypatch.setattr(httpx, "AsyncClient", _Client)

    resp = client.post(
        "/receipt/scan",
        headers={"Authorization": "Bearer route-secret"},
        json={"image": "data:image/png;base64,abc", "userId": "u1", "idempotencyKey": "k1", "countryHint": "TH"},
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True


# ---------------------------------------------------------------------------
# ingest_receipt: LINE path through the shared _post_to_convex helper
# ---------------------------------------------------------------------------


async def test_ingest_receipt_returns_404_for_unknown_user(monkeypatch, patch_settings):
    """LINE user ID reaches Convex; a 404 maps to 'User not found'."""
    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, headers=None, json=None):
            return _FakeResponse(404, {"error": "User not found"})

    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: _Client())

    result = await ingest_receipt(
        line_user_id="U_line_user",
        payload={"lines": [{"text": "MERCHANT CAFE", "conf": 85.0, "y": 0.0, "words": []}]},
        idempotency_key="line_msg_999",
    )

    assert result["success"] is False
    assert result["error"] == "User not found"


async def test_ingest_receipt_success_does_not_include_source(monkeypatch, patch_settings):
    """The LINE path must NOT include a 'source' field (unlike app-camera)."""
    captured = {}

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, headers=None, json=None):
            captured.update({"url": url, "headers": headers, "json": json})
            return _FakeResponse(200, {"success": True, "draftId": "draft_line"})

    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: _Client())

    result = await ingest_receipt(
        line_user_id="U_line_user",
        payload={"lines": []},
        idempotency_key="line_msg_888",
    )

    assert result["success"] is True
    assert "source" not in captured["json"]
    assert captured["json"]["lineUserId"] == "U_line_user"
