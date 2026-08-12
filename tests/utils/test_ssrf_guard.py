"""Tests for SSRF guard utilities."""

import socket
from unittest.mock import patch

import pytest

from src.utils.ssrf_guard import (
    assert_safe_url,
    is_private_or_reserved_ip,
    resolve_all_ips,
)


class TestIsPrivateOrReservedIP:
    """Tests for IP address classification."""

    def test_private_ipv4_ranges(self):
        """Test private IPv4 ranges are detected."""
        assert is_private_or_reserved_ip("10.0.0.1") is True
        assert is_private_or_reserved_ip("10.255.255.255") is True
        assert is_private_or_reserved_ip("172.16.0.1") is True
        assert is_private_or_reserved_ip("172.31.255.255") is True
        assert is_private_or_reserved_ip("192.168.0.1") is True
        assert is_private_or_reserved_ip("192.168.255.255") is True

    def test_loopback_ips(self):
        """Test loopback addresses are detected."""
        assert is_private_or_reserved_ip("127.0.0.1") is True
        assert is_private_or_reserved_ip("127.255.255.255") is True
        assert is_private_or_reserved_ip("::1") is True

    def test_link_local_ips(self):
        """Test link-local addresses are detected (includes cloud metadata)."""
        assert is_private_or_reserved_ip("169.254.169.254") is True  # Cloud metadata
        assert is_private_or_reserved_ip("169.254.0.1") is True
        assert is_private_or_reserved_ip("fe80::1") is True

    def test_unique_local_ipv6(self):
        """Test IPv6 unique-local addresses."""
        assert is_private_or_reserved_ip("fc00::1") is True
        assert is_private_or_reserved_ip("fd00::1") is True

    def test_public_ips_allowed(self):
        """Test public IPs are not flagged."""
        assert is_private_or_reserved_ip("8.8.8.8") is False
        assert is_private_or_reserved_ip("1.1.1.1") is False
        assert is_private_or_reserved_ip("2001:4860:4860::8888") is False  # Google DNS IPv6

    def test_invalid_ip_returns_true(self):
        """Test invalid IP format returns True (treated as unsafe)."""
        assert is_private_or_reserved_ip("not.an.ip") is True
        assert is_private_or_reserved_ip("") is True


class TestResolveAllIPs:
    """Tests for DNS resolution."""

    @patch("src.utils.ssrf_guard.socket.getaddrinfo")
    def test_resolve_ipv4(self, mock_getaddrinfo):
        """Test IPv4 resolution."""
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443)),
        ]
        ips = resolve_all_ips("dns.google")
        assert "8.8.8.8" in ips

    @patch("src.utils.ssrf_guard.socket.getaddrinfo")
    def test_resolve_ipv6(self, mock_getaddrinfo):
        """Test IPv6 resolution."""
        mock_getaddrinfo.return_value = [
            (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2001:4860:4860::8888", 443, 0, 0)),
        ]
        ips = resolve_all_ips("dns.google")
        assert "2001:4860:4860::8888" in ips

    @patch("src.utils.ssrf_guard.socket.getaddrinfo")
    def test_deduplicates_ips(self, mock_getaddrinfo):
        """Test duplicate IPs are removed."""
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443)),
        ]
        ips = resolve_all_ips("dns.google")
        assert ips.count("8.8.8.8") == 1

    @patch("src.utils.ssrf_guard.socket.getaddrinfo")
    def test_dns_failure_returns_empty(self, mock_getaddrinfo):
        """Test DNS failure returns empty list."""
        import socket as socket_module

        mock_getaddrinfo.side_effect = socket_module.gaierror("Name does not resolve")
        ips = resolve_all_ips("nonexistent.invalid")
        assert ips == []


class TestAssertSafeURL:
    """Tests for URL validation."""

    def test_valid_https_url_allowed_host(self):
        """Test valid HTTPS URL with allowed host passes."""
        url = "https://api.nousresearch.com/v1/chat/completions"
        with patch("src.utils.ssrf_guard.resolve_all_ips", return_value=["8.8.8.8"]):
            result = assert_safe_url(url)
            assert result == url

    def test_http_rejected(self):
        """Test HTTP URLs are rejected."""
        url = "http://api.nousresearch.com/v1/chat/completions"
        with pytest.raises(ValueError, match="Only HTTPS URLs are allowed"):
            assert_safe_url(url)

    def test_non_allowed_host_rejected(self):
        """Test non-allowlisted hosts are rejected."""
        url = "https://evil.com/api"
        with pytest.raises(ValueError, match="not in the allowed hosts list"):
            assert_safe_url(url)

    def test_private_ip_rejected(self):
        """Test URLs resolving to private IPs are rejected."""
        url = "https://api.nousresearch.com/api"
        with patch("src.utils.ssrf_guard.resolve_all_ips", return_value=["10.0.0.1"]):
            with pytest.raises(ValueError, match="resolves to private/reserved IP"):
                assert_safe_url(url)

    def test_cloud_metadata_ip_rejected(self):
        """Test URLs resolving to cloud metadata IP are rejected."""
        url = "https://api.nousresearch.com/api"
        with patch("src.utils.ssrf_guard.resolve_all_ips", return_value=["169.254.169.254"]):
            with pytest.raises(ValueError, match="resolves to private/reserved IP"):
                assert_safe_url(url)

    def test_localhost_rejected(self):
        """Test localhost URLs are rejected."""
        url = "https://api.nousresearch.com/api"
        with patch("src.utils.ssrf_guard.resolve_all_ips", return_value=["127.0.0.1"]):
            with pytest.raises(ValueError, match="resolves to private/reserved IP"):
                assert_safe_url(url)

    def test_dns_failure_rejected(self):
        """Test DNS resolution failure is rejected."""
        url = "https://api.nousresearch.com/api"
        with patch("src.utils.ssrf_guard.resolve_all_ips", return_value=[]):
            with pytest.raises(ValueError, match="Could not resolve hostname"):
                assert_safe_url(url)

    def test_invalid_url_format_rejected(self):
        """Test malformed URLs are rejected."""
        with pytest.raises(ValueError, match="Invalid URL format|Only HTTPS URLs are allowed"):
            assert_safe_url("not a url")

    def test_missing_hostname_rejected(self):
        """Test URLs without hostname are rejected."""
        with pytest.raises(ValueError, match="URL must have a hostname"):
            assert_safe_url("https:///path")

    def test_custom_allowed_hosts(self):
        """Test custom allowed hosts parameter."""
        url = "https://custom.api.example.com/path"
        with patch("src.utils.ssrf_guard.resolve_all_ips", return_value=["8.8.8.8"]):
            result = assert_safe_url(url, allowed_hosts={"custom.api.example.com"})
            assert result == url
