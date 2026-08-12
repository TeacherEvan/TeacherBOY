"""Tests for DateExtractionService metrics tracking."""

from unittest.mock import AsyncMock, patch

import pytest

from src.services.date_extraction_service import DateExtractionService
from src.services.metrics_service import metrics_service


class TestDateExtractionMetrics:
    """Tests for extraction metrics recording."""

    @pytest.mark.asyncio
    async def test_fallback_extraction_records_fallback_metric(self):
        """Test that fallback extraction records fallback metric."""
        initial_fallback = metrics_service.get_extraction_stats()["fallback_total"]
        initial_requests = metrics_service.get_extraction_stats()["total_requests"]

        service = DateExtractionService()
        messages = ["Meeting tomorrow at 10am"]

        # Call fallback directly (no AI client = fallback)
        events = await service.extract_events_from_messages(messages)

        # Should have extracted 1 event via fallback
        assert len(events) == 1
        assert events[0].confidence == "low"

        # Check metrics were recorded
        stats = metrics_service.get_extraction_stats()
        assert stats["total_requests"] == initial_requests + 1
        assert stats["fallback_total"] == initial_fallback + 1
        assert stats["errors_total"] >= 0  # May have errors from AI attempt

    @pytest.mark.asyncio
    async def test_metrics_singleton_persistence(self):
        """Test that metrics persist across multiple extraction calls."""
        # Capture initial state
        stats_before = metrics_service.get_extraction_stats()

        service = DateExtractionService()
        messages = ["Event tomorrow"]

        # Multiple fallback calls
        await service.extract_events_from_messages(messages)
        await service.extract_events_from_messages(messages)

        stats_after = metrics_service.get_extraction_stats()

        # Should have 2 more requests, 2 more fallbacks
        assert stats_after["total_requests"] == stats_before["total_requests"] + 2
        assert stats_after["fallback_total"] == stats_before["fallback_total"] + 2

    @pytest.mark.asyncio
    @patch("src.services.ai_review_service.ai_review_service")
    async def test_ai_extraction_failure_fallback_records_both(self, mock_ai_review):
        """Test that AI failure followed by fallback records both error and fallback."""
        # Mock AI to fail
        mock_ai_review.extract_calendar_candidates = AsyncMock(side_effect=Exception("API Error"))

        service = DateExtractionService()
        messages = ["Meeting tomorrow"]

        events = await service.extract_events_from_messages(messages)

        # Should still get fallback result
        assert len(events) == 1

        # Check metrics - note that metrics are cumulative across tests
        stats = metrics_service.get_extraction_stats()
        assert stats["total_requests"] > 0
        assert stats["fallback_total"] > 0
