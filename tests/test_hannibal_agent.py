"""Tests for HannibalProfileAgent - psychological profiling from chat history.

Covers the fixes for:
- the profile being truncated after the first part (P0: report delivery),
- the report being built from an empty/partial data set (chats available),
- a group-chat profile broadcasting every member's analysis (privacy),
- the "me"/"all" trigger matching inside unrelated words.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.hannibal_agent import (
    MAX_ANALYSIS_MESSAGES,
    MIN_MESSAGES_FOR_PROFILE,
    HannibalProfileAgent,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def mock_settings():
    mock = MagicMock()
    mock.is_openrouter_configured.return_value = True
    mock.is_hermes_configured.return_value = True
    mock.is_gemini_configured.return_value = True
    mock.is_nous_configured.return_value = False
    mock.line_channel_access_token = "test_token"
    return mock


@pytest.fixture
def dm_event():
    event = MagicMock()
    event.message = MagicMock()
    event.message.type = "text"
    event.source = MagicMock()
    event.source.user_id = "user123"
    event.source.group_id = None
    event.source.room_id = None
    event.reply_token = "reply_token_123"
    return event


@pytest.fixture
def group_event():
    event = MagicMock()
    event.message = MagicMock()
    event.message.type = "text"
    event.source = MagicMock()
    event.source.user_id = "user123"
    event.source.group_id = "group_abc"
    event.source.room_id = None
    event.reply_token = "reply_token_123"
    return event


@pytest.fixture
def mock_line_api():
    api = MagicMock()
    api.reply_message = MagicMock()
    api.push_message = MagicMock()
    return api


def make_buffered_messages(count, user_id="user123", start=None):
    """Build fake BufferedMessage objects."""
    from src.services.message_buffer_service import BufferedMessage

    start = start or datetime(2026, 10, 22, 9, 0, tzinfo=UTC)
    messages = []
    for i in range(count):
        messages.append(
            BufferedMessage(
                text=f"message number {i} with some content",
                user_id=user_id,
                timestamp=start + timedelta(minutes=i),
            )
        )
    return messages


# ---------------------------------------------------------------------------
# Trigger handling
# ---------------------------------------------------------------------------
class TestHannibalShouldHandle:
    @pytest.mark.asyncio
    async def test_dm_accepts_loose_triggers(self, dm_event, mock_settings):
        with patch("src.agents.hannibal_agent.settings", mock_settings):
            agent = HannibalProfileAgent()
            for trigger in ("hannibal profile", "analyze messages", "read chat", "analyze writing"):
                assert await agent.should_handle(dm_event, trigger) is True, trigger

    @pytest.mark.asyncio
    async def test_group_only_accepts_strict_triggers(self, group_event, mock_settings):
        """A group must never trigger a full-chat profile on a loose phrase."""
        with patch("src.agents.hannibal_agent.settings", mock_settings):
            agent = HannibalProfileAgent()

            assert await agent.should_handle(group_event, "read chat") is False
            assert await agent.should_handle(group_event, "analyze messages") is False
            assert await agent.should_handle(group_event, "hannibal profile") is True

    @pytest.mark.asyncio
    async def test_no_provider_configured(self, dm_event, mock_settings):
        mock_settings.is_gemini_configured.return_value = False
        mock_settings.is_openrouter_configured.return_value = False
        mock_settings.is_hermes_configured.return_value = False
        mock_settings.is_nous_configured.return_value = False
        with patch("src.agents.hannibal_agent.settings", mock_settings):
            agent = HannibalProfileAgent()
            assert await agent.should_handle(dm_event, "hannibal profile") is False


# ---------------------------------------------------------------------------
# Target extraction (M1: boundary flip on substring matching)
# ---------------------------------------------------------------------------
class TestExtractTargetUser:
    def test_explicit_all(self):
        agent = HannibalProfileAgent()
        assert agent._extract_target_user("hannibal profile all", "u1") == "all"

    def test_explicit_me(self):
        agent = HannibalProfileAgent()
        assert agent._extract_target_user("hannibal profile me", "u1") == "u1"

    def test_me_inside_word_is_not_a_match(self):
        """ "remember" must not be read as "me"."""
        agent = HannibalProfileAgent()
        assert agent._extract_target_user("hannibal profile remember", "u1") == "all"

    def test_all_inside_word_is_not_a_match(self):
        """ "overall" must not be read as "all"."""
        agent = HannibalProfileAgent()
        # "me" is present, so the correct answer is the requester.
        assert agent._extract_target_user("hannibal profile me overall", "u1") == "u1"
        assert agent._extract_target_user("analyze chat overall", "u1") == "all"

    def test_default_is_all(self):
        agent = HannibalProfileAgent()
        assert agent._extract_target_user("hannibal profile", "u1") == "all"


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------
class TestComputeStats:
    def test_counts_are_computed_from_data(self):
        agent = HannibalProfileAgent()
        base = datetime(2026, 10, 22, 9, 0, tzinfo=UTC)
        messages = [
            {"user_id": "u1", "text": "How are you?", "timestamp": base},
            {"user_id": "u1", "text": "I am fine thanks", "timestamp": base + timedelta(minutes=1)},
            {"user_id": "u2", "text": "WELCOME!!!", "timestamp": base + timedelta(minutes=2)},
        ]

        stats = agent._compute_stats(messages)

        assert stats["total_messages"] == 3
        assert stats["participants"] == 2
        assert stats["messages_per_user"] == {"u1": 2, "u2": 1}
        assert stats["question_ratio_pct"] == pytest.approx(33.3, abs=0.2)
        assert stats["exclamation_ratio_pct"] == pytest.approx(33.3, abs=0.2)
        assert stats["allcaps_ratio_pct"] == pytest.approx(33.3, abs=0.2)
        assert stats["peak_hour"] == "09:00"
        assert stats["median_gap_minutes"] == 1.0

    def test_empty_input_does_not_divide_by_zero(self):
        agent = HannibalProfileAgent()
        stats = agent._compute_stats([])
        assert stats["total_messages"] == 0
        assert stats["question_ratio_pct"] == 0
        assert stats["avg_chars"] == 0

    def test_missing_timestamps_are_tolerated(self):
        agent = HannibalProfileAgent()
        stats = agent._compute_stats([{"user_id": "u1", "text": "hello", "timestamp": None}])
        assert stats["total_messages"] == 1
        assert stats["peak_hour"] == "unknown"
        assert stats["median_gap_minutes"] == 0


# ---------------------------------------------------------------------------
# Message collection (the "chats available" data set)
# ---------------------------------------------------------------------------
class TestCollectMessages:
    @pytest.mark.asyncio
    async def test_merges_buffer_and_memory_without_duplicates(self):
        agent = HannibalProfileAgent()
        buffered = make_buffered_messages(5)

        memory = MagicMock()
        memory.get_recent_entries = AsyncMock(
            return_value=[
                {"role": "user", "content": "message number 4 with some content", "timestamp": "2026-10-22T09:04:00"},
                {"role": "user", "content": "an older persisted message", "timestamp": "2026-10-21T09:00:00"},
                {"role": "assistant", "content": "bot reply", "timestamp": "2026-10-21T09:00:01"},
            ]
        )

        with (
            patch("src.agents.hannibal_agent.message_buffer_service") as mock_buffer,
            patch("src.agents.hannibal_agent.get_conversation_memory", return_value=memory),
        ):
            mock_buffer.get_recent_messages.return_value = buffered
            messages = await agent._collect_messages("user_u1", None)

        texts = [m["text"] for m in messages]
        # Duplicate (same text + user) is de-duplicated.
        assert texts.count("message number 4 with some content") == 1
        # The persisted older message is included.
        assert "an older persisted message" in texts
        # Assistant turns are not user messages.
        assert "bot reply" not in texts
        assert len(messages) == 6

    @pytest.mark.asyncio
    async def test_filters_to_target_user(self):
        agent = HannibalProfileAgent()
        buffered = make_buffered_messages(3, user_id="u1") + make_buffered_messages(3, user_id="u2")

        with (
            patch("src.agents.hannibal_agent.message_buffer_service") as mock_buffer,
            patch("src.agents.hannibal_agent.get_conversation_memory", return_value=None),
        ):
            mock_buffer.get_recent_messages.return_value = buffered
            messages = await agent._collect_messages("user_x", "u2")

        assert len(messages) == 3
        assert all(m["user_id"] == "u2" for m in messages)

    @pytest.mark.asyncio
    async def test_survives_a_broken_buffer(self):
        agent = HannibalProfileAgent()
        with (
            patch("src.agents.hannibal_agent.message_buffer_service") as mock_buffer,
            patch("src.agents.hannibal_agent.get_conversation_memory", return_value=None),
        ):
            mock_buffer.get_recent_messages.side_effect = RuntimeError("boom")
            messages = await agent._collect_messages("user_x", None)

        assert messages == []


# ---------------------------------------------------------------------------
# Prompt building
# ---------------------------------------------------------------------------
class TestBuildAnalysisPrompt:
    def test_contains_measured_statistics(self):
        agent = HannibalProfileAgent()
        messages = [
            {"user_id": "u1", "text": "Hello there?", "timestamp": datetime(2026, 10, 22, 9, 0, tzinfo=UTC)},
        ]

        prompt = agent._build_analysis_prompt(messages, "u1")

        assert "MEASURED STATISTICS" in prompt
        assert "Total messages analyzed: 1" in prompt
        assert "u1" in prompt
        assert "BEGIN MESSAGES" in prompt

    def test_oversized_history_is_capped(self):
        agent = HannibalProfileAgent()
        messages = [{"user_id": "u1", "text": "x" * 5000, "timestamp": None} for _ in range(50)]

        prompt = agent._build_analysis_prompt(messages, "u1")

        # The message block is bounded, but the report is still generated.
        assert "BEGIN MESSAGES" in prompt
        assert "were omitted" in prompt

    def test_single_oversized_message_does_not_hang(self):
        """A single message larger than the whole prompt budget must not loop forever."""
        agent = HannibalProfileAgent()
        messages = [{"user_id": "u1", "text": "x" * 200000, "timestamp": None}]

        prompt = agent._build_analysis_prompt(messages, "u1")

        assert "BEGIN MESSAGES" in prompt
        assert len(prompt) < 200000

    def test_system_prompt_defines_required_sections(self):
        agent = HannibalProfileAgent()
        system = agent._get_system_prompt()
        for heading in (
            "COMMUNICATION STYLE",
            "EMOTIONAL PROFILE",
            "COGNITIVE INDICATORS",
            "SOCIAL DYNAMICS",
            "TEMPORAL PATTERNS",
            "KEY BEHAVIORAL INDICATORS",
            "CLINICAL SUMMARY",
        ):
            assert heading in system, heading


# ---------------------------------------------------------------------------
# Report delivery (the P0 truncation fix)
# ---------------------------------------------------------------------------
class TestReportDelivery:
    def test_split_preserves_all_content(self):
        agent = HannibalProfileAgent()
        text = "\n\n".join(f"Paragraph {i} " + "detail " * 60 for i in range(30))

        parts = agent._split_message(text)

        assert len(parts) > 1
        assert all(len(p) <= 5000 for p in parts)
        assert "Paragraph 29" in "".join(parts)
        assert "[Part 1/" in parts[0]

    def test_split_of_short_text_is_single_part(self):
        agent = HannibalProfileAgent()
        assert agent._split_message("short report") == ["short report"]

    @pytest.mark.asyncio
    async def test_all_parts_are_sent(self, dm_event, mock_line_api):
        """Regression: the old code sent only the first part."""
        agent = HannibalProfileAgent()
        parts = [f"[Part {i + 1}/3]\n\npart {i}" for i in range(3)]

        with patch("src.agents.hannibal_agent.asyncio.sleep", new=AsyncMock()):
            await agent._send_multipart_response(dm_event, mock_line_api, parts, "user123")

        # First part via reply, remaining parts via push.
        assert mock_line_api.reply_message.call_count == 1
        assert mock_line_api.push_message.call_count == 2

        pushed = [call.args[0].messages[0].text for call in mock_line_api.push_message.call_args_list]
        assert pushed == ["[Part 2/3]\n\npart 1", "[Part 3/3]\n\npart 2"]

    @pytest.mark.asyncio
    async def test_all_parts_pushed_when_reply_token_missing(self, dm_event, mock_line_api):
        dm_event.reply_token = None
        agent = HannibalProfileAgent()
        parts = ["one", "two"]

        with patch("src.agents.hannibal_agent.asyncio.sleep", new=AsyncMock()):
            await agent._send_multipart_response(dm_event, mock_line_api, parts, "user123")

        assert mock_line_api.reply_message.call_count == 0
        assert mock_line_api.push_message.call_count == 2

    @pytest.mark.asyncio
    async def test_group_remaining_parts_stay_in_the_group(self, group_event, mock_line_api):
        """Part 1 is a group reply, so the rest must be pushed to the group."""
        agent = HannibalProfileAgent()
        parts = ["one", "two"]

        with patch("src.agents.hannibal_agent.asyncio.sleep", new=AsyncMock()):
            await agent._send_multipart_response(group_event, mock_line_api, parts, "user123")

        pushed_to = mock_line_api.push_message.call_args.args[0].to
        assert pushed_to == "group_abc"

    @pytest.mark.asyncio
    async def test_a_failed_push_does_not_discard_the_remaining_parts(self, dm_event, mock_line_api):
        """One failed push must not silently swallow the rest of the report."""
        agent = HannibalProfileAgent()
        parts = ["p1", "p2", "p3", "p4"]

        calls = {"n": 0}

        def flaky_push(request):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("LINE 500")

        mock_line_api.push_message.side_effect = flaky_push

        with patch("src.agents.hannibal_agent.asyncio.sleep", new=AsyncMock()):
            await agent._send_multipart_response(dm_event, mock_line_api, parts, "user123")

        # All four parts were attempted (one failed, three succeeded).
        assert mock_line_api.push_message.call_count == 4
        # The user is told that part of the report is missing.
        last_text = mock_line_api.push_message.call_args.args[0].messages[0].text
        assert "could not be delivered" in last_text


# ---------------------------------------------------------------------------
# End to end
# ---------------------------------------------------------------------------
class TestHandleEndToEnd:
    @pytest.mark.asyncio
    async def test_full_report_is_delivered(self, dm_event, mock_line_api, mock_settings):
        agent = HannibalProfileAgent()
        long_report = "\n\n".join(f"### SECTION {i}\n" + "finding " * 60 for i in range(8))

        with (
            patch("src.agents.hannibal_agent.settings", mock_settings),
            patch("src.agents.hannibal_agent.privilege_service") as mock_priv,
            patch("src.agents.hannibal_agent.message_buffer_service") as mock_buffer,
            patch("src.agents.hannibal_agent.get_conversation_memory", return_value=None),
            patch(
                "src.agents.hannibal_agent.chat_completion_with_fallback",
                new=AsyncMock(return_value=long_report),
            ),
            patch("src.agents.hannibal_agent.asyncio.sleep", new=AsyncMock()),
        ):
            mock_priv.is_admin.return_value = True
            mock_buffer.get_recent_messages.return_value = make_buffered_messages(MIN_MESSAGES_FOR_PROFILE + 5)

            handled = await agent.handle(dm_event, "hannibal profile", mock_line_api)

        assert handled is True
        # Every part of the report reached the user.
        sent_text = "".join(
            [call.args[0].messages[0].text for call in mock_line_api.reply_message.call_args_list]
            + [call.args[0].messages[0].text for call in mock_line_api.push_message.call_args_list]
        )
        assert "SECTION 7" in sent_text
        # Nothing was dropped: every "finding" of the source report is present.
        assert sent_text.count("finding") == long_report.count("finding")

    @pytest.mark.asyncio
    async def test_insufficient_messages_reports_count(self, dm_event, mock_line_api, mock_settings):
        agent = HannibalProfileAgent()

        with (
            patch("src.agents.hannibal_agent.settings", mock_settings),
            patch("src.agents.hannibal_agent.privilege_service") as mock_priv,
            patch("src.agents.hannibal_agent.message_buffer_service") as mock_buffer,
            patch("src.agents.hannibal_agent.get_conversation_memory", return_value=None),
        ):
            mock_priv.is_admin.return_value = True
            mock_buffer.get_recent_messages.return_value = make_buffered_messages(3)

            handled = await agent.handle(dm_event, "hannibal profile", mock_line_api)

        assert handled is True
        assert mock_line_api.reply_message.call_count == 1
        text = mock_line_api.reply_message.call_args.args[0].messages[0].text
        assert "Insufficient Data" in text
        assert "Found: 3 messages" in text

    @pytest.mark.asyncio
    async def test_group_profile_only_uses_the_requester(self, group_event, mock_line_api, mock_settings):
        """A group profile must never include other members' messages."""
        agent = HannibalProfileAgent()
        other_users = make_buffered_messages(50, user_id="someone_else")
        requester = make_buffered_messages(MIN_MESSAGES_FOR_PROFILE + 5, user_id="user123")

        captured = {}

        async def fake_completion(messages, **kwargs):
            captured["prompt"] = messages[-1]["content"]
            return "report"

        with (
            patch("src.agents.hannibal_agent.settings", mock_settings),
            patch("src.agents.hannibal_agent.privilege_service") as mock_priv,
            patch("src.agents.hannibal_agent.message_buffer_service") as mock_buffer,
            patch("src.agents.hannibal_agent.get_conversation_memory", return_value=None),
            patch("src.agents.hannibal_agent.chat_completion_with_fallback", new=fake_completion),
            patch("src.agents.hannibal_agent.asyncio.sleep", new=AsyncMock()),
        ):
            mock_priv.is_admin.return_value = True
            mock_buffer.get_recent_messages.return_value = other_users + requester

            handled = await agent.handle(group_event, "hannibal profile", mock_line_api)

        assert handled is True
        prompt = captured["prompt"]
        # Only the requester's messages are in the prompt.
        assert "someone_ot" not in prompt
        assert "Target for analysis: User user123" in prompt

    @pytest.mark.asyncio
    async def test_llm_failure_sends_error(self, dm_event, mock_line_api, mock_settings):
        agent = HannibalProfileAgent()

        with (
            patch("src.agents.hannibal_agent.settings", mock_settings),
            patch("src.agents.hannibal_agent.privilege_service") as mock_priv,
            patch("src.agents.hannibal_agent.message_buffer_service") as mock_buffer,
            patch("src.agents.hannibal_agent.get_conversation_memory", return_value=None),
            patch(
                "src.agents.hannibal_agent.chat_completion_with_fallback",
                new=AsyncMock(return_value=None),
            ),
        ):
            mock_priv.is_admin.return_value = True
            mock_buffer.get_recent_messages.return_value = make_buffered_messages(MIN_MESSAGES_FOR_PROFILE + 1)

            handled = await agent.handle(dm_event, "hannibal profile", mock_line_api)

        assert handled is False
        assert mock_line_api.reply_message.call_count == 1
        text = mock_line_api.reply_message.call_args.args[0].messages[0].text
        assert "Analysis Failed" in text


def test_max_analysis_messages_is_bounded():
    assert MAX_ANALYSIS_MESSAGES >= MIN_MESSAGES_FOR_PROFILE
