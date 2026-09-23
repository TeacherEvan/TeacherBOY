"""Tests for external vision service."""

import pytest

from src.services import external_vision_service as svc


def test_build_task_prompt_custom():
    assert svc.build_task_prompt("ocr", "custom") == "custom"


def test_parse_structured_json():
    assert svc.parse_structured_json('{"a":1}') == {"a": 1}
    assert svc.parse_structured_json("none") is None


@pytest.mark.asyncio
async def test_analyze_receipt(monkeypatch):
    async def fake(messages, **kw):
        return ("COFFEE 45 THB", "gemini")
    monkeypatch.setattr(svc, "chat_completion_with_vision_fallback_ex", fake)
    out = await svc.analyze_image_task(image_data_url="data:img", task="receipt")
    assert out["provider"] == "gemini"
    assert out["ocr"]["engine"] == "gemini-vision@1"
