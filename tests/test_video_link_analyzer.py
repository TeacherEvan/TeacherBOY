"""Tests for VideoLinkAnalyzerService."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.video_link_analyzer_service import VideoLinkAnalyzerService


@pytest.mark.asyncio
async def test_extract_video_link():
    service = VideoLinkAnalyzerService()

    # YouTube url
    text1 = "Hey, check this out: https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert service.extract_video_link(text1) == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    # TikTok url
    text2 = "Some text before https://tiktok.com/@user/video/12345 and text after"
    assert service.extract_video_link(text2) == "https://tiktok.com/@user/video/12345"

    # No url
    text3 = "No video link here"
    assert service.extract_video_link(text3) is None


@pytest.mark.asyncio
async def test_fetch_oembed_youtube():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "title": "Rick Astley - Never Gonna Give You Up (Official Music Video)",
        "author_name": "Rick Astley",
        "provider_name": "YouTube",
    }

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response

    service = VideoLinkAnalyzerService(http_client=mock_client)
    res = await service.fetch_oembed("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    assert res is not None
    assert res["title"] == "Rick Astley - Never Gonna Give You Up (Official Music Video)"
    mock_client.get.assert_called_once_with(
        "https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v=dQw4w9WgXcQ&format=json",
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
    )


@pytest.mark.asyncio
async def test_fetch_html_metadata():
    html_content = """
    <html>
        <head>
            <title>My Cool Page Title</title>
            <meta property="og:description" content="This is an awesome description of the page." />
            <meta property="og:site_name" content="MyPlatform" />
        </head>
        <body></body>
    </html>
    """
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = html_content

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response

    service = VideoLinkAnalyzerService(http_client=mock_client)
    metadata = await service.fetch_html_metadata("https://example.com/video")

    assert metadata["title"] == "My Cool Page Title"
    assert metadata["description"] == "This is an awesome description of the page."
    assert metadata["provider_name"] == "MyPlatform"


@pytest.mark.asyncio
async def test_analyze_video_link_success():
    service = VideoLinkAnalyzerService()

    # Mock dependencies
    service.fetch_oembed = AsyncMock(
        return_value={"title": "Mock Video Title", "description": "This is a video about testing.", "provider_name": "YouTube"}
    )

    with patch("src.services.video_link_analyzer_service.chat_completion_with_fallback", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = "This is a great video about unit tests on YouTube."

        summary = await service.analyze_video_link("https://youtube.com/watch?v=123")

        assert summary == "This is a great video about unit tests on YouTube."
        mock_llm.assert_called_once()
        # Verify prompt details in calls
        args, kwargs = mock_llm.call_args
        messages = args[0]
        assert "Mock Video Title" in messages[1]["content"]
        assert "YouTube" in messages[1]["content"]
