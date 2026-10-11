"""HTTP-status RSS failures degrade quietly; malformed feeds stay loud."""

import httpx
import pytest

from src.services.news_data_service import NewsDataService


class _RaisingClient:
    def __init__(self, status_code: int):
        self._status = status_code

    async def get(self, url, timeout=None, follow_redirects=None):
        request = httpx.Request("GET", url)
        response = httpx.Response(self._status, request=request)
        raise httpx.HTTPStatusError("blocked", request=request, response=response)


@pytest.mark.asyncio
async def test_rss_http_error_logs_warning_not_error(caplog):
    service = NewsDataService(http_client=None, news_api_key=None)
    service.client = _RaisingClient(451)

    with caplog.at_level("WARNING"):
        items = await service._parse_rss_feed("https://www.bangkokpost.com/rss/data/thailand.xml")

    assert items[0]["title"] == "News unavailable"
    assert any("RSS feed unavailable (HTTP 451)" in record.message for record in caplog.records)
    assert not any(record.levelname == "ERROR" for record in caplog.records)
