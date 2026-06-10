# tests/test_image_analyzer_session_manager_hf.py
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import shutil
from pathlib import Path


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
