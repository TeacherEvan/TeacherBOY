"""Video Link Analyzer Service - Extracts metadata and summarizes video links."""

import logging
import re
from typing import Any

import httpx

from src.utils.llm_fallback import chat_completion_with_fallback

logger = logging.getLogger(__name__)

# Video link detection pattern - matches YouTube, TikTok, Vimeo, Facebook, and Instagram links
VIDEO_LINK_PATTERN = re.compile(
    r"https?://(?:www\.)?(?:" r"youtube\.com|youtu\.be|tiktok\.com|vimeo\.com|facebook\.com|instagram\.com" r")\S*",
    re.IGNORECASE,
)


class VideoLinkAnalyzerService:
    """Service to fetch video link metadata and generate a structured summary using LLM fallback chain."""

    def __init__(self, http_client: httpx.AsyncClient | None = None):
        self._client = http_client or httpx.AsyncClient(timeout=10.0, follow_redirects=True)

    def extract_video_link(self, text: str) -> str | None:
        """Extract the first video link from text."""
        match = VIDEO_LINK_PATTERN.search(text)
        return match.group(0) if match else None

    def has_video_link(self, text: str) -> bool:
        """Check if text contains a video link."""
        return bool(VIDEO_LINK_PATTERN.search(text))

    async def fetch_oembed(self, url: str) -> dict[str, Any] | None:
        """Fetch oEmbed metadata for supported platforms (YouTube, TikTok, Vimeo)."""
        lower_url = url.lower()
        endpoint = None

        if "youtube.com" in lower_url or "youtu.be" in lower_url:
            endpoint = f"https://www.youtube.com/oembed?url={url}&format=json"
        elif "vimeo.com" in lower_url:
            endpoint = f"https://vimeo.com/api/oembed.json?url={url}"
        elif "tiktok.com" in lower_url:
            endpoint = f"https://www.tiktok.com/oembed?url={url}"

        if not endpoint:
            return None

        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            response = await self._client.get(endpoint, headers=headers)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            logger.warning(f"Failed to fetch oEmbed for {url}: {e}")

        return None

    def _get_meta_content(self, html: str, name_or_property: str) -> str | None:
        # Match <meta property="name_or_property" content="value"> or <meta name="name_or_property" content="value">
        pattern = rf'<meta\s+[^>]*?(?:property|name)=["\']{re.escape(name_or_property)}["\']\s+[^>]*?content=["\'](.*?)["\']'
        match = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
        if not match:
            pattern_rev = (
                rf'<meta\s+[^>]*?content=["\'](.*?)["\']\s+[^>]*?(?:property|name)=["\']{re.escape(name_or_property)}["\']'
            )
            match = re.search(pattern_rev, html, re.IGNORECASE | re.DOTALL)
        return match.group(1).strip() if match else None

    async def fetch_html_metadata(self, url: str) -> dict[str, Any]:
        """Fetch general page HTML and extract metadata using regexes."""
        metadata = {}
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            response = await self._client.get(url, headers=headers)
            if response.status_code == 200:
                html = response.text

                # Extract title
                title_match = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
                title = title_match.group(1).strip() if title_match else None
                og_title = self._get_meta_content(html, "og:title")

                metadata["title"] = og_title or title or "Video Link"

                # Extract description
                desc = self._get_meta_content(html, "description")
                og_desc = self._get_meta_content(html, "og:description")
                metadata["description"] = og_desc or desc or ""

                # Extract provider
                og_site_name = self._get_meta_content(html, "og:site_name")
                metadata["provider_name"] = og_site_name or ""
        except Exception as e:
            logger.warning(f"Failed to fetch HTML metadata for {url}: {e}")

        return metadata

    async def analyze_video_link(self, url: str) -> str | None:
        """Fetch metadata, analyze using LLM, and return summary/context."""
        # 1. Fetch metadata
        metadata = await self.fetch_oembed(url)
        if not metadata:
            metadata = await self.fetch_html_metadata(url)

        if not metadata:
            logger.warning(f"Could not retrieve any metadata for video URL: {url}")
            return None

        title = metadata.get("title") or "Unknown Title"
        description = metadata.get("description") or metadata.get("author_name") or ""
        provider = metadata.get("provider_name") or "Video Platform"

        # Determine platform where it's from
        platform = provider
        if not platform:
            if "youtube.com" in url.lower() or "youtu.be" in url.lower():
                platform = "YouTube"
            elif "tiktok.com" in url.lower():
                platform = "TikTok"
            elif "vimeo.com" in url.lower():
                platform = "Vimeo"
            elif "facebook.com" in url.lower() or "fb.watch" in url.lower():
                platform = "Facebook"
            elif "instagram.com" in url.lower():
                platform = "Instagram"
            else:
                platform = "Video Sharing Site"

        # 2. Build prompt for LLM
        prompt = (
            f"Please analyze and summarize the following video/link information:\n"
            f"URL: {url}\n"
            f"Title: {title}\n"
            f"Platform: {platform}\n"
            f"Description/Context: {description}\n\n"
            f"Under the following constraints, formulate a helpful and structured response for the user:\n"
            f"1. Explain where the video is from (the platform, creator/author if known).\n"
            f"2. Summarize what it is for/about (main topic, theme, context).\n"
            f"3. Provide any useful context surrounding the link or platform based on the description.\n"
            f"4. Keep the summary professional, clear, and concise."
        )

        messages = [
            {
                "role": "system",
                "content": "You are Ms. Green. You analyze video/link information based on metadata. You do not analyze actual video frames/pixels, but summarize the context, author, and description of the linked video for the user.",
            },
            {"role": "user", "content": prompt},
        ]

        # Call LLM fallback chain
        summary = await chat_completion_with_fallback(messages, temperature=0.7)
        return summary


# Singleton instance
video_link_analyzer_service = VideoLinkAnalyzerService()
