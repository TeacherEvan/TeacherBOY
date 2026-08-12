"""Tests for enhanced metrics service functionality."""

from datetime import datetime

from src.services.metrics_service import MetricsService, MetricsSnapshot


class TestMetricsService:
    """Test metrics service tracking and snapshot functionality."""

    def test_record_translation_with_chat_id(self):
        """Test translation recording with chat_id tracking."""
        service = MetricsService()

        # Record translations from different chats
        service.record_translation("google", "user_123")
        service.record_translation("google", "user_456")
        service.record_translation("libre", "group_789")

        snap = service.snapshot()
        assert snap.translation_requests_total == 3
        assert snap.translation_google_total == 2
        assert snap.translation_libre_total == 1
        assert snap.unique_users_count == 2
        assert snap.unique_groups_count == 1

    def test_record_news_request_with_chat_id(self):
        """Test news request recording with chat_id tracking."""
        service = MetricsService()

        # Record news requests from different chats
        service.record_news_request("user_123")
        service.record_news_request("user_123")  # Same user
        service.record_news_request("group_456")

        snap = service.snapshot()
        assert snap.news_requests_total == 3
        assert snap.unique_users_count == 1
        assert snap.unique_groups_count == 1

    def test_record_rate_limited(self):
        """Test rate-limited request tracking."""
        service = MetricsService()

        service.record_rate_limited()
        service.record_rate_limited()
        service.record_rate_limited()

        snap = service.snapshot()
        assert snap.rate_limited_requests == 3

    def test_record_failed_translation(self):
        """Test failed translation tracking."""
        service = MetricsService()

        service.record_failed_translation()
        service.record_failed_translation()

        snap = service.snapshot()
        assert snap.failed_translations == 2

    def test_record_admin_command(self):
        """Test admin command execution tracking."""
        service = MetricsService()

        service.record_admin_command()
        service.record_admin_command()
        service.record_admin_command()

        snap = service.snapshot()
        assert snap.admin_commands_total == 3

    def test_peak_hour_tracking(self):
        """Test peak hour tracking from hourly buckets."""
        service = MetricsService()

        # Simulate requests at different hours
        # We'll manipulate hourly_requests directly for testing
        service._hourly_requests[10] = 5
        service._hourly_requests[14] = 15
        service._hourly_requests[18] = 10

        snap = service.snapshot()
        assert snap.peak_hour == 14
        assert snap.peak_hour_requests == 15

    def test_cache_metrics(self):
        """Test cache hit/miss tracking."""
        service = MetricsService()

        service.record_cache_hit()
        service.record_cache_hit()
        service.record_cache_hit()
        service.record_cache_miss()

        snap = service.snapshot()
        assert snap.cache_hits_total == 3
        assert snap.cache_misses_total == 1

    def test_unique_users_deduplication(self):
        """Test that unique users are properly deduplicated."""
        service = MetricsService()

        # Same user multiple times
        service.record_translation("google", "user_123")
        service.record_translation("google", "user_123")
        service.record_translation("libre", "user_123")
        service.record_news_request("user_123")

        snap = service.snapshot()
        assert snap.unique_users_count == 1

    def test_unique_groups_deduplication(self):
        """Test that unique groups are properly deduplicated."""
        service = MetricsService()

        # Same group multiple times
        service.record_translation("google", "group_456")
        service.record_translation("google", "group_456")
        service.record_news_request("group_456")

        snap = service.snapshot()
        assert snap.unique_groups_count == 1

    def test_mixed_users_and_groups(self):
        """Test tracking of both users and groups."""
        service = MetricsService()

        service.record_translation("google", "user_111")
        service.record_translation("google", "user_222")
        service.record_translation("google", "group_333")
        service.record_news_request("user_444")
        service.record_news_request("group_555")

        snap = service.snapshot()
        assert snap.unique_users_count == 3  # user_111, user_222, user_444
        assert snap.unique_groups_count == 2  # group_333, group_555

    def test_snapshot_type(self):
        """Test that snapshot returns correct type."""
        service = MetricsService()
        snap = service.snapshot()

        assert isinstance(snap, MetricsSnapshot)
        assert isinstance(snap.started_at, datetime)
        assert isinstance(snap.translation_requests_total, int)
        assert isinstance(snap.unique_users_count, int)

    def test_no_chat_id_tracking(self):
        """Test recording without chat_id doesn't crash."""
        service = MetricsService()

        # These should work without chat_id
        service.record_translation("google", None)
        service.record_translation("google")
        service.record_news_request(None)
        service.record_news_request()

        snap = service.snapshot()
        assert snap.translation_requests_total == 2
        assert snap.news_requests_total == 2
        assert snap.unique_users_count == 0
        assert snap.unique_groups_count == 0

    def test_peak_hour_with_no_requests(self):
        """Test peak hour calculation when no requests recorded."""
        service = MetricsService()

        snap = service.snapshot()
        assert snap.peak_hour is None
        assert snap.peak_hour_requests == 0

    def test_all_metrics_integration(self):
        """Integration test with all metric types."""
        service = MetricsService()

        # Translations
        service.record_translation("google", "user_1")
        service.record_translation("google", "user_2")
        service.record_translation("libre", "group_1")

        # News
        service.record_news_request("user_1")
        service.record_news_request("group_2")

        # Failures
        service.record_failed_translation()
        service.record_rate_limited()
        service.record_rate_limited()

        # Admin commands
        service.record_admin_command()

        # Cache
        service.record_cache_hit()
        service.record_cache_hit()
        service.record_cache_miss()

        snap = service.snapshot()

        # Verify all metrics
        assert snap.translation_requests_total == 3
        assert snap.translation_google_total == 2
        assert snap.translation_libre_total == 1
        assert snap.news_requests_total == 2
        assert snap.failed_translations == 1
        assert snap.rate_limited_requests == 2
        assert snap.admin_commands_total == 1
        assert snap.unique_users_count == 2
        assert snap.unique_groups_count == 2
        assert snap.cache_hits_total == 2
        assert snap.cache_misses_total == 1
