from datetime import date, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

from src.agents.review_agent import ReviewAgent
from src.services.calendar_service import CalendarEvent
from src.services.convex_staff_memory_repository import (
    ConvexStaffMemoryRepository,
)
from src.services.message_buffer_service import MessageBufferService
from src.services.staff_memory_service import StaffMemoryService


@pytest.mark.asyncio
async def test_review_agent_translates_last_non_english_message_and_pushes_dm(
    tmp_path: Path,
):
    line_api = Mock()
    line_api.push_message = Mock()
    line_api.reply_message = Mock()

    event = Mock()
    event.reply_token = "reply"
    event.source = Mock()
    event.source.user_id = "U_REQ"
    event.source.group_id = "G1"
    event.source.type = "group"

    buffer_service = MessageBufferService()
    buffer_service.store_message("group_G1", "ประชุมวันศุกร์", "U_OTHER")

    ai_review_service = AsyncMock()
    ai_review_service.translate_and_summarize.return_value = (
        "Friday meeting summary"
    )

    agent = ReviewAgent(
        ai_review_service=ai_review_service,
        message_buffer=buffer_service,
        staff_memory_service=StaffMemoryService(
            tmp_path / "staff_memory.json"
        ),
    )

    handled = await agent.handle(
        event,
        "Ms. Green review",
        line_api,
    )

    assert handled is True
    assert line_api.reply_message.called
    assert line_api.push_message.called


@pytest.mark.asyncio
async def test_review_agent_ignores_bot_buffered_messages(tmp_path: Path):
    line_api = Mock()
    line_api.push_message = Mock()
    line_api.reply_message = Mock()

    event = Mock()
    event.reply_token = "reply"
    event.source = Mock()
    event.source.user_id = "U_REQ"
    event.source.group_id = "G1"
    event.source.type = "group"

    buffer_service = MessageBufferService()
    buffer_service.store_message("group_G1", "ประชุมวันศุกร์", "U_OTHER")
    buffer_service.store_message("group_G1", "สรุปโดยบอท", "BOT")

    ai_review_service = AsyncMock()
    ai_review_service.translate_and_summarize.return_value = (
        "Friday meeting summary"
    )

    agent = ReviewAgent(
        ai_review_service=ai_review_service,
        message_buffer=buffer_service,
        staff_memory_service=StaffMemoryService(
            tmp_path / "staff_memory.json"
        ),
        bot_user_id="BOT",
    )

    handled = await agent.handle(event, "Ms. Green review", line_api)

    assert handled is True
    ai_review_service.translate_and_summarize.assert_awaited_once_with(
        "ประชุมวันศุกร์"
    )


@pytest.mark.asyncio
async def test_review_agent_answers_who_do_you_work_for(tmp_path: Path):
    line_api = Mock()
    line_api.reply_message = Mock()
    line_api.push_message = Mock()

    event = Mock()
    event.reply_token = "reply"
    event.source = Mock()
    event.source.user_id = "U_REQ"
    event.source.type = "user"

    agent = ReviewAgent(
        ai_review_service=AsyncMock(),
        message_buffer=MessageBufferService(),
        staff_memory_service=StaffMemoryService(
            tmp_path / "staff_memory.json"
        ),
    )

    handled = await agent.handle(event, "Ms. Green who do you work for?", line_api)

    assert handled is True
    assert line_api.reply_message.called
    request = line_api.reply_message.call_args[0][0]
    assert (
        "I am purely a hardworking assistant and at the service of all KPS "
        "employees."
        in request.messages[0].text
    )


@pytest.mark.asyncio
async def test_review_agent_keeps_existing_pending_review(tmp_path: Path):
    line_api = Mock()
    line_api.push_message = Mock()
    line_api.reply_message = Mock()

    event = Mock()
    event.reply_token = "reply"
    event.source = Mock()
    event.source.user_id = "U_REQ"
    event.source.group_id = "G1"
    event.source.type = "group"

    buffer_service = MessageBufferService()
    buffer_service.store_message("group_G1", "ข้อความแรก", "U_OTHER")

    ai_review_service = AsyncMock()
    ai_review_service.translate_and_summarize.return_value = "First summary"

    agent = ReviewAgent(
        ai_review_service=ai_review_service,
        message_buffer=buffer_service,
        staff_memory_service=StaffMemoryService(
            tmp_path / "staff_memory.json"
        ),
    )

    first_handled = await agent.handle(event, "Ms. Green review", line_api)
    assert first_handled is True

    buffer_service.store_message("group_G1", "ข้อความใหม่", "U_OTHER")
    second_handled = await agent.handle(event, "Ms. Green review", line_api)

    assert second_handled is True
    ai_review_service.translate_and_summarize.assert_awaited_once_with(
        "ข้อความแรก"
    )
    assert agent._pending_reviews["U_REQ"].summary == "First summary"
    latest_reply = line_api.reply_message.call_args[0][0]
    assert (
        latest_reply.messages[0].text
        == "Please finish the pending review in your DM before starting a new one."
    )


@pytest.mark.asyncio
async def test_review_agent_saves_memory_choice_through_convex_repository(
    tmp_path: Path,
):
    line_api = Mock()
    line_api.push_message = Mock()
    line_api.reply_message = Mock()

    review_event = Mock()
    review_event.reply_token = "reply-review"
    review_event.source = Mock()
    review_event.source.user_id = "U_REQ"
    review_event.source.group_id = "G1"
    review_event.source.type = "group"

    dm_event = Mock()
    dm_event.reply_token = "reply-dm"
    dm_event.source = Mock()
    dm_event.source.user_id = "U_REQ"
    dm_event.source.type = "user"

    buffer_service = MessageBufferService()
    buffer_service.store_message("group_G1", "ประชุมวันศุกร์", "U_OTHER")

    ai_review_service = AsyncMock()
    ai_review_service.translate_and_summarize.return_value = (
        "Friday meeting summary"
    )

    convex_client = AsyncMock()
    created_payload = {}

    def post_side_effect(path, payload):
        created_payload.clear()
        created_payload.update(payload)
        return {"data": dict(payload)}

    convex_client.post.side_effect = post_side_effect
    staff_memory_service = StaffMemoryService(
        tmp_path / "staff_memory.json",
        repository=ConvexStaffMemoryRepository(convex_client=convex_client),
    )

    agent = ReviewAgent(
        ai_review_service=ai_review_service,
        message_buffer=buffer_service,
        staff_memory_service=staff_memory_service,
    )

    first_handled = await agent.handle(review_event, "Ms. Green review", line_api)
    second_handled = await agent.handle(dm_event, "memory", line_api)

    assert first_handled is True
    assert second_handled is True
    convex_client.post.assert_awaited_once()
    assert created_payload["title"] == "Friday meeting summary"
    assert created_payload["summary"] == "Friday meeting summary"
    assert created_payload["priority"] == "P1"
    assert created_payload["dueDate"] is None
    assert created_payload["sourceChatId"] == "group_G1"
    assert created_payload["createdBy"] == "U_REQ"
    assert isinstance(created_payload["itemId"], str)
    assert created_payload["itemId"]


@pytest.mark.asyncio
async def test_review_agent_reports_memory_save_failures_and_keeps_pending_review(
    tmp_path: Path,
):
    line_api = Mock()
    line_api.push_message = Mock()
    line_api.reply_message = Mock()

    review_event = Mock()
    review_event.reply_token = "reply-review"
    review_event.source = Mock()
    review_event.source.user_id = "U_REQ"
    review_event.source.group_id = "G1"
    review_event.source.type = "group"

    dm_event = Mock()
    dm_event.reply_token = "reply-dm"
    dm_event.source = Mock()
    dm_event.source.user_id = "U_REQ"
    dm_event.source.type = "user"

    buffer_service = MessageBufferService()
    buffer_service.store_message("group_G1", "ประชุมวันศุกร์", "U_OTHER")

    ai_review_service = AsyncMock()
    ai_review_service.translate_and_summarize.return_value = (
        "Friday meeting summary"
    )

    staff_memory_service = StaffMemoryService(tmp_path / "staff_memory.json")
    staff_memory_service.add_item_async = AsyncMock(  # type: ignore[method-assign]
        side_effect=RuntimeError("convex unavailable")
    )

    agent = ReviewAgent(
        ai_review_service=ai_review_service,
        message_buffer=buffer_service,
        staff_memory_service=staff_memory_service,
    )

    first_handled = await agent.handle(review_event, "Ms. Green review", line_api)
    second_handled = await agent.handle(dm_event, "memory", line_api)

    assert first_handled is True
    assert second_handled is True
    assert "U_REQ" in agent._pending_reviews
    latest_reply = line_api.reply_message.call_args[0][0]
    assert latest_reply.messages[0].text == (
        "I couldn\'t save that to memory right now. Please try again."
    )


@pytest.mark.asyncio
async def test_review_agent_prunes_stale_pending_reviews(tmp_path: Path):
    line_api = Mock()
    line_api.push_message = Mock()
    line_api.reply_message = Mock()

    event = Mock()
    event.reply_token = "reply"
    event.source = Mock()
    event.source.user_id = "U_REQ"
    event.source.group_id = "G1"
    event.source.type = "group"

    buffer_service = MessageBufferService()
    buffer_service.store_message("group_G1", "ข้อความเก่า", "U_OTHER")

    ai_review_service = AsyncMock()
    ai_review_service.translate_and_summarize.return_value = "Stale summary"

    agent = ReviewAgent(
        ai_review_service=ai_review_service,
        message_buffer=buffer_service,
        staff_memory_service=StaffMemoryService(
            tmp_path / "staff_memory.json"
        ),
    )

    # Manually add a stale pending review
    stale_time = datetime.now() - timedelta(hours=25)  # Older than 24 hours TTL
    agent._pending_reviews["U_REQ"] = PendingReview(
        original_text="stale message",
        summary="Stale summary",
        source_chat_id="group_G1",
        created_at=stale_time,
    )

    # Trigger handle, which should prune stale reviews
    await agent.handle(event, "Ms. Green whats important this week?", line_api)

    assert "U_REQ" not in agent._pending_reviews
    # Ensure no review was generated, as the stale one should have been pruned
    ai_review_service.translate_and_summarize.assert_not_awaited()


@pytest.mark.asyncio
async def test_review_agent_summarizes_weekly_priorities(
    tmp_path: Path,
):
    line_api = Mock()
    line_api.reply_message = Mock()
    line_api.push_message = Mock()

    event = Mock()
    event.reply_token = "reply"
    event.source = Mock()
    event.source.user_id = "U_REQ"
    event.source.type = "user"

    today = date.today()
    convex_client = AsyncMock()
    convex_client.post.return_value = {
        "data": [
            {
                "itemId": "memory-1",
                "title": "Flag ceremony practice",
                "summary": "Flag ceremony practice this week",
                "priority": "P1",
                "dueDate": today.isoformat(),
                "sourceChatId": "group_G1",
                "createdBy": "U_REQ",
            }
        ]
    }
    staff_memory = StaffMemoryService(
        tmp_path / "staff_memory.json",
        repository=ConvexStaffMemoryRepository(convex_client=convex_client),
    )

    calendar_service = Mock()
    calendar_service.get_user_events_async = AsyncMock(return_value=[
        CalendarEvent(
            event_id="1",
            user_id="U_REQ",
            chat_id="user_U_REQ",
            title="Exam papers due",
            event_date=today,
            reminder_days=[1, 0],
            is_friend=True,
        )
    ])

    agent = ReviewAgent(
        ai_review_service=AsyncMock(),
        message_buffer=MessageBufferService(),
        staff_memory_service=staff_memory,
        calendar_service_instance=calendar_service,
    )

    handled = await agent.handle(
        event,
        "Ms. Green whats important this week?",
        line_api,
    )

    assert handled is True
    convex_client.post.assert_awaited_once_with(
        "/records/listStaffMemoryItemsForWeek",
        {
            "weekStart": today.isoformat(),
            "weekEnd": (today + timedelta(days=6)).isoformat(),
        },
    )
    request = line_api.reply_message.call_args[0][0]
    assert "Flag ceremony practice" in request.messages[0].text
    assert "Exam papers due" in request.messages[0].text
