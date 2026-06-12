"""Tests for HistoryLogService log viewer features."""

import pytest
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

from src.services.history_log_service import (
    HistoryLogService,
    EventType,
    LogLevel,
    DatePreset,
    AccessLevel,
)


class TestHistoryLogServicePresets:
    """Tests for DatePreset and query_logs_preset."""

    @pytest.fixture
    def log_service(self):
        """Create a log service with in-memory storage only."""
        return HistoryLogService(storage_path="./test_logs", enable_file_storage=False)

    @pytest.mark.asyncio
    async def test_query_logs_preset_today(self, log_service):
        """Test querying logs for today preset."""
        now = datetime.now(UTC)
        yesterday = now - timedelta(days=1)

        # Add test logs in specific order
        await log_service.log(EventType.USER_MESSAGE, "msg1", LogLevel.INFO, chat_id="chat1")
        # Manually set one to yesterday
        first_key = list(log_service._logs.keys())[0]
        log_service._logs[first_key].timestamp = yesterday

        await log_service.log(EventType.BOT_RESPONSE, "msg2", LogLevel.INFO, chat_id="chat1")

        results = await log_service.query_logs_preset(DatePreset.TODAY)
        assert len(results) == 1
        assert results[0]["message"] == "msg2"  # Most recent first

    @pytest.mark.asyncio
    async def test_query_logs_preset_yesterday(self, log_service):
        """Test querying logs for yesterday preset."""
        now = datetime.now(UTC)
        yesterday = now - timedelta(days=1)
        two_days_ago = now - timedelta(days=2)

        # Add logs with today's timestamp first
        await log_service.log(EventType.USER_MESSAGE, "today_msg", LogLevel.INFO)
        # Add yesterday message
        await log_service.log(EventType.USER_MESSAGE, "yesterday_msg", LogLevel.INFO)
        # Add a very old message
        await log_service.log(EventType.USER_MESSAGE, "old_msg", LogLevel.INFO)

        keys = list(log_service._logs.keys())
        # keys[0] = oldest (first added) = today_msg
        # keys[1] = middle = yesterday_msg
        # keys[2] = newest (last added) = old_msg
        log_service._logs[keys[0]].timestamp = now  # today
        log_service._logs[keys[1]].timestamp = yesterday
        log_service._logs[keys[2]].timestamp = two_days_ago

        results = await log_service.query_logs_preset(DatePreset.YESTERDAY)
        # Iterates in reverse (most recent first), so order: old_msg, yesterday_msg, today_msg
        # Only yesterday_msg falls in yesterday's range
        assert len(results) == 1
        assert results[0]["message"] == "yesterday_msg"

    @pytest.mark.asyncio
    async def test_query_logs_preset_last_7_days(self, log_service):
        """Test querying logs for last 7 days preset."""
        now = datetime.now(UTC)
        eight_days_ago = now - timedelta(days=8)
        three_days_ago = now - timedelta(days=3)

        await log_service.log(EventType.USER_MESSAGE, "recent", LogLevel.INFO)
        await log_service.log(EventType.USER_MESSAGE, "old", LogLevel.INFO)

        keys = list(log_service._logs.keys())
        log_service._logs[keys[0]].timestamp = three_days_ago
        log_service._logs[keys[1]].timestamp = eight_days_ago

        results = await log_service.query_logs_preset(DatePreset.LAST_7_DAYS)
        assert len(results) == 1
        assert results[0]["message"] == "recent"

    @pytest.mark.asyncio
    async def test_query_logs_preset_last_30_days(self, log_service):
        """Test querying logs for last 30 days preset."""
        now = datetime.now(UTC)
        forty_days_ago = now - timedelta(days=40)
        ten_days_ago = now - timedelta(days=10)

        await log_service.log(EventType.USER_MESSAGE, "recent", LogLevel.INFO)
        await log_service.log(EventType.USER_MESSAGE, "old", LogLevel.INFO)

        keys = list(log_service._logs.keys())
        log_service._logs[keys[0]].timestamp = ten_days_ago
        log_service._logs[keys[1]].timestamp = forty_days_ago

        results = await log_service.query_logs_preset(DatePreset.LAST_30_DAYS)
        assert len(results) == 1
        assert results[0]["message"] == "recent"

    @pytest.mark.asyncio
    async def test_query_logs_preset_custom_raises(self, log_service):
        """Test that CUSTOM preset raises ValueError."""
        with pytest.raises(ValueError, match="Unknown preset"):
            await log_service.query_logs_preset(DatePreset.CUSTOM)

    def test_date_preset_enum_values(self):
        """Test DatePreset enum has expected values."""
        assert DatePreset.TODAY == "today"
        assert DatePreset.YESTERDAY == "yesterday"
        assert DatePreset.LAST_7_DAYS == "last_7_days"
        assert DatePreset.LAST_30_DAYS == "last_30_days"
        assert DatePreset.CUSTOM == "custom"


class TestHistoryLogServiceFlexBuilders:
    """Tests for Flex message bubble builders."""

    @pytest.fixture
    def log_service(self):
        return HistoryLogService(storage_path="./test_logs", enable_file_storage=False)

    @pytest.mark.asyncio
    async def test_build_log_flex_bubble(self, log_service):
        """Test building log viewer Flex bubble."""
        await log_service.log(EventType.USER_MESSAGE, "test msg", LogLevel.INFO, chat_id="chat1")
        await log_service.log(EventType.ERROR, "error msg", LogLevel.ERROR, chat_id="chat1")

        logs = await log_service.query_logs(limit=10)
        bubble = log_service.build_log_flex_bubble(
            logs=logs,
            preset=DatePreset.LAST_7_DAYS,
            filters={},
            page=1,
            total_pages=1
        )

        assert bubble["type"] == "bubble"
        assert bubble["size"] == "giga"
        assert "header" in bubble
        assert "body" in bubble
        assert "footer" in bubble

        # Check header content
        header_texts = [c["text"] for c in bubble["header"]["contents"] if c["type"] == "text"]
        assert any("Admin Logs" in t for t in header_texts)
        assert any("Last 7 Days" in t for t in header_texts)  # .title() capitalizes each word

        # Check body has log entries
        body_contents = bubble["body"]["contents"]
        log_entries = [c for c in body_contents if c.get("type") == "text" and "test msg" in c.get("text", "")]
        assert len(log_entries) > 0

    def test_build_date_picker_bubble(self, log_service):
        """Test building custom date picker Flex bubble."""
        bubble = log_service.build_date_picker_bubble(DatePreset.CUSTOM)

        assert bubble["type"] == "bubble"
        assert "body" in bubble

        # Find datetimepicker buttons recursively in body contents
        def find_datetimepicker_buttons(contents):
            buttons = []
            for item in contents:
                if item.get("type") == "button" and item.get("action", {}).get("type") == "datetimepicker":
                    buttons.append(item)
                elif "contents" in item:
                    buttons.extend(find_datetimepicker_buttons(item["contents"]))
            return buttons

        dp_buttons = find_datetimepicker_buttons(bubble["body"]["contents"])
        assert len(dp_buttons) == 2  # start + end date pickers

        # Check for Apply and Cancel buttons
        def find_postback_buttons(contents, data):
            buttons = []
            for item in contents:
                if item.get("type") == "button" and item.get("action", {}).get("data") == data:
                    buttons.append(item)
                elif "contents" in item:
                    buttons.extend(find_postback_buttons(item["contents"], data))
            return buttons

        apply_btn = find_postback_buttons(bubble["body"]["contents"], "logs_custom_apply")
        cancel_btn = find_postback_buttons(bubble["body"]["contents"], "logs_cancel")
        assert len(apply_btn) == 1
        assert len(cancel_btn) == 1


class TestHistoryLogServiceQuickReplies:
    """Tests for quick-reply configuration."""

    @pytest.fixture
    def log_service(self):
        return HistoryLogService(storage_path="./test_logs", enable_file_storage=False)

    def test_get_log_quick_reply_items(self, log_service):
        """Test quick-reply items for log viewer."""
        items = log_service.get_log_quick_reply_items()

        from linebot.v3.messaging import QuickReplyItem, PostbackAction

        assert len(items) == 5
        for item in items:
            assert isinstance(item, QuickReplyItem)
            assert isinstance(item.action, PostbackAction)
            assert item.action.data.startswith("logs_preset=") or item.action.data == "logs_custom_range"

        labels = [item.action.label for item in items]
        assert "Today" in labels
        assert "Yesterday" in labels
        assert "Last 7 days" in labels
        assert "Last 30 days" in labels
        assert "Custom range..." in labels

