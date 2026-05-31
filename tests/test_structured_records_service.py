from unittest.mock import AsyncMock

import pytest

from src.services.structured_records_service import StructuredRecordsService


@pytest.mark.asyncio
async def test_upsert_user_posts_expected_payload() -> None:
    convex_client = AsyncMock()
    convex_client.post.return_value = {"ok": True}
    service = StructuredRecordsService(convex_client=convex_client)

    result = await service.upsert_user(
        line_user_id="U123",
        display_name="Alice",
        role="friend",
    )

    assert result == {"ok": True}
    convex_client.post.assert_awaited_once_with(
        "/records/upsertUser",
        {
            "lineUserId": "U123",
            "displayName": "Alice",
            "role": "friend",
        },
    )


@pytest.mark.asyncio
async def test_record_interaction_posts_expected_payload() -> None:
    convex_client = AsyncMock()
    convex_client.post.return_value = {"ok": True}
    service = StructuredRecordsService(convex_client=convex_client)

    result = await service.record_interaction(
        line_user_id="U123",
        source_chat_id="group_G123",
        message_type="text",
        direction="inbound",
        text_preview="hello there",
        handled_agent="HelpAgent",
    )

    assert result == {"ok": True}
    convex_client.post.assert_awaited_once_with(
        "/records/appendInteraction",
        {
            "lineUserId": "U123",
            "sourceChatId": "group_G123",
            "messageType": "text",
            "direction": "inbound",
            "textPreview": "hello there",
            "handledAgent": "HelpAgent",
        },
    )