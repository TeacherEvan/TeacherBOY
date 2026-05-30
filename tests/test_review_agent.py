from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

from src.agents.review_agent import ReviewAgent
from src.services.calendar_service import CalendarEvent
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
        "KPS review",
        line_api,
    )

    assert handled is True
    assert line_api.reply_message.called
    assert line_api.push_message.called


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

    handled = await agent.handle(event, "KPS who do you work for?", line_api)

    assert handled is True
    assert line_api.reply_message.called
    request = line_api.reply_message.call_args[0][0]
    assert (
        "I am purely a hardworking assitant and at the service of all KPS "
        "employees."
        in request.messages[0].text
    )


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

    staff_memory = StaffMemoryService(tmp_path / "staff_memory.json")
    today = date.today()
    staff_memory.add_item(
        title="Flag ceremony practice",
        summary="Flag ceremony practice this week",
        priority="P1",
        due_date=today,
        source_chat_id="group_G1",
        created_by="U_REQ",
    )

    calendar_service = Mock()
    calendar_service.get_user_events.return_value = [
        CalendarEvent(
            event_id="1",
            user_id="U_REQ",
            chat_id="user_U_REQ",
            title="Exam papers due",
            event_date=today,
            reminder_days=[1, 0],
            is_friend=True,
        )
    ]

    agent = ReviewAgent(
        ai_review_service=AsyncMock(),
        message_buffer=MessageBufferService(),
        staff_memory_service=staff_memory,
        calendar_service_instance=calendar_service,
    )

    handled = await agent.handle(
        event,
        "KPS whats important this week?",
        line_api,
    )

    assert handled is True
    request = line_api.reply_message.call_args[0][0]
    assert "Flag ceremony practice" in request.messages[0].text
    assert "Exam papers due" in request.messages[0].text
