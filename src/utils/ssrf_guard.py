"""SSRF (Server-Side Request Forgery) protection utilities.

This module provides safe URL validation to prevent SSRF attacks by:
- Enforcing HTTPS only
- Blocking private/reserved IP ranges (including cloud metadata 169.254.169.254)
- Validating against allowlisted hosts
- Disallowing redirects
"""

import logging
import socket
from ipaddress import IPv4Address, IPv6Address, ip_address
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Default allowed hosts for external API calls
DEFAULT_ALLOWED_HOSTS: set[str] = {
    "api.nousresearch.com",
    "openrouter.ai",
    "api.github.com",
    "generativelanguage.googleapis.com",
    "api.brave.com",
    "huggingface.co",
    "api.huggingface.co",
}


def is_private_or_reserved_ip(ip_str: str) -> bool:
    """Check if an IP address is private, reserved, or loopback.
    
    Covers:
    - IPv4 private ranges (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16)
    - IPv4 loopback (127.0.0.0/8)
    - IPv4 link-local (169.254.0.0/16) - includes cloud metadata 169.254.169.254
    - IPv6 loopback (::1)
    - IPv6 unique-local (fc00::/7)
    - IPv6 link-local (fe80::/10)
    - IPv6 multicast (ff00::/8)
    - IPv4 multicast (224.0.0.0/4)
    - IPv4 broadcast (255.255.255.255)
    - Unspecified addresses (0.0.0.0, ::)
    """
    try:
        ip = ip_address(ip_str)
    except ValueError:
        logger.warning(f"Invalid IP address format: {ip_str}")
        return True  # Treat invalid IPs as unsafe

    if isinstance(ip, IPv4Address):
        return (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        )
    elif isinstance(ip, IPv6Address):
        return (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
            or ip.is_site_local
        )
    return True  # Should not happen


def resolve_all_ips(hostname: str) -> list[str]:
    """Resolve all IP addresses for a hostname (both IPv4 and IPv6).
    
    Uses getaddrinfo to get all addresses, which is what actual HTTP clients use.
    """
    try:
        infos = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        ips = []
        for info in infos:
            ip = info[4][0]
            if ip not in ips:
                ips.append(ip)
        return ips
    except socket.gaierror as e:
        logger.warning(f"DNS resolution failed for {hostname}: {e}")
        return []


def assert_safe_url(
    url: str,
    allowed_hosts: Optional[set[str]] = None,
    allow_redirects: bool = False,
) -> str:
    """Validate a URL is safe for server-side fetching.
    
    Args:
        url: The URL to validate
        allowed_hosts: Optional set of allowed hostnames. If None, uses DEFAULT_ALLOWED_HOSTS.
        allow_redirects: Whether to allow HTTP redirects (default: False for security)
    
    Returns:
        The validated URL string
        
    Raises:
        ValueError: If the URL fails any safety check
    """
    if allowed_hosts is None:
        allowed_hosts = DEFAULT_ALLOWED_HOSTS

    try:
        parsed = urlparse(url)
    except Exception as e:
        raise ValueError(f"Invalid URL format: {e}")

    # Enforce HTTPS only
    if parsed.scheme != "https":
        raise ValueError(f"Only HTTPS URLs are allowed, got: {parsed.scheme}")

    # Check hostname
    hostname = parsed.hostname or ""
    if not hostname:
        raise ValueError("URL must have a hostname")

    # Normalize hostname (lowercase)
    hostname = hostname.lower()

    # Check against allowlist
    if hostname not in allowed_hosts:
        raise ValueError(f"Host '{hostname}' is not in the allowed hosts list")

    # Resolve ALL IPs for the hostname and check each one
    resolved_ips = resolve_all_ips(hostname)
    if not resolved_ips:
        raise ValueError(f"Could not resolve hostname: {hostname}")

    for ip in resolved_ips:
        if is_private_or_reserved_ip(ip):
            logger.error(f"SSRF attempt blocked: {hostname} resolves to private/reserved IP: {ip}")
            raise ValueError(f"Host '{hostname}' resolves to private/reserved IP: {ip}")

    # Disallow redirects unless explicitly allowed
    if not allow_redirects:
        # Note: Actual redirect prevention is done at the HTTP client level
        # This is a validation hint
        pass

    return url


async def safe_fetch(
    client,
    url: str,
    allowed_hosts: Optional[set[str]] = None,
    **kwargs
):
    """Safely fetch a URL with SSRF protection.
    
    Args:
        client: httpx.AsyncClient instance
        url: URL to fetch
        allowed_hosts: Optional allowed hosts set
        **kwargs: Additional arguments passed to client.get()
    
    Returns:
        httpx.Response
        
    Raises:
        ValueError: If URL fails safety checks
        httpx.HTTPError: On HTTP errors
    """
    validated_url = assert_safe_url(url, allowed_hosts)
    
    # Ensure redirects are not followed
    kwargs.setdefault("follow_redirects", False)
    
    return await client.get(validated_url, **kwargs)