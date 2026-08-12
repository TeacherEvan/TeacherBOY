# tests/test_image_analyzer_session_manager_hf.py
# tests/test_image_analyzer_session_manager_hf.py
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def clean_test_data():
    """Clean up test data directory before and after each test."""
    test_path = Path("./data/images")
    if test_path.exists():
        shutil.rmtree(test_path)
    yield
    if test_path.exists():
        shutil.rmtree(test_path)


@pytest.mark.asyncio
async def test_hf_storage_setup_called_when_configured():
    from src.services.image_analyzer_session_manager import ImageAnalyzerSessionManager

    with patch("huggingface_hub.HfApi"), patch("huggingface_hub.CommitScheduler"):
        mgr = ImageAnalyzerSessionManager(hf_token="test_token", hf_repo_id="EvilEvan/teacherboy-images")
    assert mgr._images_hf_enabled is True


@pytest.mark.asyncio
async def test_hf_storage_disabled_without_token():
    from src.services.image_analyzer_session_manager import ImageAnalyzerSessionManager

    mgr = ImageAnalyzerSessionManager(hf_token=None, hf_repo_id="EvilEvan/teacherboy-images")
    assert mgr._images_hf_enabled is False


@pytest.mark.asyncio
async def test_hf_storage_disabled_without_repo_id():
    from src.services.image_analyzer_session_manager import ImageAnalyzerSessionManager

    mgr = ImageAnalyzerSessionManager(hf_token="test_token", hf_repo_id=None)
    assert mgr._images_hf_enabled is False


@pytest.mark.asyncio
async def test_save_image_metadata_writes_local_json():
    from src.services.image_analyzer_session_manager import ImageAnalyzerSessionManager

    mgr = ImageAnalyzerSessionManager(hf_token="test_token", hf_repo_id="EvilEvan/teacherboy-images")
    with patch("huggingface_hub.HfApi"), patch("huggingface_hub.CommitScheduler"):
        mgr._setup_images_hf_storage()
    await mgr.save_image_metadata(
        chat_id="user_123",
        image_base64="data:image/jpeg;base64,abc",
        prompt="What is this?",
        response="A menu",
        analysis_mode="standard",
        duration_ms=500,
        image_size_bytes=1234,
        model_used="openai/gpt-4o",
    )
    # Check local file exists
    files = list(Path("./data/images").rglob("*.json"))
    assert len(files) == 1


@pytest.mark.asyncio
async def test_save_image_metadata_creates_hashed_chat_dir():
    from src.services.image_analyzer_session_manager import ImageAnalyzerSessionManager

    mgr = ImageAnalyzerSessionManager(hf_token="test_token", hf_repo_id="EvilEvan/teacherboy-images")
    with patch("huggingface_hub.HfApi"), patch("huggingface_hub.CommitScheduler"):
        mgr._setup_images_hf_storage()
    await mgr.save_image_metadata(
        chat_id="user_123",
        image_base64="data:image/jpeg;base64,abc",
        prompt="What is this?",
        response="A menu",
        analysis_mode="standard",
        duration_ms=500,
        image_size_bytes=1234,
        model_used="openai/gpt-4o",
    )
    # Check file is in hashed chat directory
    files = list(Path("./data/images").rglob("*.json"))
    assert len(files) == 1
    # Filename should be in a subdirectory (hashed chat_id)
    assert len(files[0].relative_to("./data/images").parts) == 2  # hashed_chat_id / image_id.json


@pytest.mark.asyncio
async def test_save_image_metadata_idempotent_unique_ids():
    from src.services.image_analyzer_session_manager import ImageAnalyzerSessionManager

    mgr = ImageAnalyzerSessionManager(hf_token="test_token", hf_repo_id="EvilEvan/teacherboy-images")
    with patch("huggingface_hub.HfApi"), patch("huggingface_hub.CommitScheduler"):
        mgr._setup_images_hf_storage()
    # Save twice with same params - should create two files with different IDs
    await mgr.save_image_metadata(
        chat_id="user_123",
        image_base64="data:image/jpeg;base64,abc",
        prompt="What is this?",
        response="A menu",
        analysis_mode="standard",
        duration_ms=500,
        image_size_bytes=1234,
        model_used="openai/gpt-4o",
    )
    await mgr.save_image_metadata(
        chat_id="user_123",
        image_base64="data:image/jpeg;base64,abc",
        prompt="What is this?",
        response="A menu",
        analysis_mode="standard",
        duration_ms=500,
        image_size_bytes=1234,
        model_used="openai/gpt-4o",
    )
    files = list(Path("./data/images").rglob("*.json"))
    assert len(files) == 2


@pytest.mark.asyncio
async def test_save_image_metadata_includes_all_fields():
    import json

    from src.services.image_analyzer_session_manager import ImageAnalyzerSessionManager

    mgr = ImageAnalyzerSessionManager(hf_token="test_token", hf_repo_id="EvilEvan/teacherboy-images")
    with patch("huggingface_hub.HfApi"), patch("huggingface_hub.CommitScheduler"):
        mgr._setup_images_hf_storage()
    await mgr.save_image_metadata(
        chat_id="user_123",
        image_base64="data:image/jpeg;base64,abc",
        prompt="What is this?",
        response="A menu",
        analysis_mode="debrief",
        duration_ms=1500,
        image_size_bytes=2048,
        model_used="openai/gpt-4o-mini",
    )
    files = list(Path("./data/images").rglob("*.json"))
    with open(files[0]) as f:
        data = json.load(f)
    assert data["chat_id"] == "user_123"
    assert data["prompt"] == "What is this?"
    assert data["response"] == "A menu"
    assert data["analysis_mode"] == "debrief"
    assert data["duration_ms"] == 1500
    assert data["image_size_bytes"] == 2048
    assert data["model_used"] == "openai/gpt-4o-mini"
    assert "timestamp" in data
    assert "id" in data
    assert data["hashed_chat_id"] == mgr._hash_chat_id("user_123")


@pytest.mark.asyncio
async def test_thread_safety_concurrent_saves():
    import asyncio

    from src.services.image_analyzer_session_manager import ImageAnalyzerSessionManager

    mgr = ImageAnalyzerSessionManager(hf_token="test_token", hf_repo_id="EvilEvan/teacherboy-images")
    with patch("huggingface_hub.HfApi"), patch("huggingface_hub.CommitScheduler"):
        mgr._setup_images_hf_storage()

    # Concurrent saves from different tasks
    async def save_task(i):
        await mgr.save_image_metadata(
            chat_id=f"user_{i}",
            image_base64=f"data:image/jpeg;base64,abc{i}",
            prompt=f"Question {i}",
            response=f"Answer {i}",
            analysis_mode="standard",
            duration_ms=100,
            image_size_bytes=100,
            model_used="openai/gpt-4o",
        )

    await asyncio.gather(*[save_task(i) for i in range(10)])
    files = list(Path("./data/images").rglob("*.json"))
    assert len(files) == 10
