"""Ollama provider integration tests."""

from __future__ import annotations

import pytest
from src.services.ollama_service import OllamaService

pytestmark = pytest.mark.asyncio


class FakeClient:
    def __init__(self, response_json, *, raise_on_post=False):
        self._response = response_json
        self.raise_on_post = raise_on_post
        self.calls = 0

    async def post(self, url, json):
        self.calls += 1
        if self.raise_on_post:
            raise RuntimeError("unreachable")
        response = _FakeResponse(self._response)
        return response

    async def aclose(self):
        pass


class _FakeResponse:
    def __init__(self, json_data):
        self._json = json_data

    def raise_for_status(self):
        return None

    def json(self):
        return self._json


@pytest.fixture()
def ollama() -> OllamaService:
    svc = OllamaService.__new__(OllamaService)
    svc.base_url = "http://localhost:11434"
    svc.default_model = "test-model"
    svc.timeout = 60.0
    svc._client = FakeClient({"choices": [{"message": {"role": "assistant", "content": "Hello World"}}]})
    return svc


class TestOllamaService:
    async def test_chat_completion_success(self, ollama: OllamaService) -> None:
        text = await ollama.chat_completion(messages=[{"role": "user", "content": "hi"}])
        assert text == "Hello World"

    async def test_chat_completion_empty_choices(self, ollama: OllamaService) -> None:
        ollama._client = FakeClient({"choices": []})
        text = await ollama.chat_completion(messages=[{"role": "user", "content": "hi"}])
        assert text is None

    async def test_chat_completion_connection_failure(self, ollama: OllamaService) -> None:
        ollama._client = FakeClient({}, raise_on_post=True)
        with pytest.raises(RuntimeError):
            await ollama.chat_completion(messages=[{"role": "user", "content": "hi"}])
