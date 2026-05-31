from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from src.services.convex_client import ConvexApiError, ConvexClient


@pytest.mark.asyncio
async def test_post_sends_bearer_token_and_json_payload() -> None:
    http_client = AsyncMock()
    response = Mock()
    response.status_code = 200
    response.json.return_value = {"ok": True}
    http_client.post.return_value = response

    client = ConvexClient(
        base_url="https://convex.example.site",
        sync_token="sync-token-123",
        http_client=http_client,
        timeout_seconds=12.0,
    )

    result = await client.post("/api/sync", {"cursor": "abc"})

    assert result == {"ok": True}
    http_client.post.assert_awaited_once_with(
        "https://convex.example.site/api/sync",
        headers={
            "Authorization": "Bearer sync-token-123",
            "Content-Type": "application/json",
        },
        json={"cursor": "abc"},
        timeout=12.0,
    )


@pytest.mark.asyncio
async def test_post_raises_convex_api_error_for_non_200_response() -> None:
    http_client = AsyncMock()
    response = Mock()
    response.status_code = 503
    response.text = "service unavailable"
    http_client.post.return_value = response

    client = ConvexClient(
        base_url="https://convex.example.site",
        sync_token="sync-token-123",
        http_client=http_client,
    )

    with pytest.raises(ConvexApiError, match="503.*service unavailable"):
        await client.post("/api/sync", {"cursor": "abc"})


@pytest.mark.asyncio
async def test_healthcheck_returns_true_for_200_response() -> None:
    http_client = AsyncMock()
    response = Mock()
    response.status_code = 200
    http_client.get.return_value = response

    client = ConvexClient(
        base_url="https://convex.example.site",
        sync_token="sync-token-123",
        http_client=http_client,
        timeout_seconds=7.5,
    )

    assert await client.healthcheck() is True
    http_client.get.assert_awaited_once_with(
        "https://convex.example.site/health",
        headers={"Authorization": "Bearer sync-token-123"},
        timeout=7.5,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "side_effect",
    [
        httpx.TransportError("network down"),
        RuntimeError("event loop stopped"),
    ],
)
async def test_healthcheck_returns_false_for_transport_or_runtime_failure(
    side_effect: Exception,
) -> None:
    http_client = AsyncMock()
    http_client.get.side_effect = side_effect

    client = ConvexClient(
        base_url="https://convex.example.site",
        sync_token="sync-token-123",
        http_client=http_client,
    )

    assert await client.healthcheck() is False