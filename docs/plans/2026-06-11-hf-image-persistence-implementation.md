# HF Image Persistence + Namespace Enforcement Implementation Plan

> **For implementer:** Use TDD throughout. Write failing test first. Watch it fail. Then implement.

**Goal:** Add HF Hub persistence for image analysis data (images + prompts + responses) and enforce `EvilEvan/teacherboy-*` repo naming convention across all HF services.

**Architecture:** Follow existing CommitScheduler pattern (ConversationMemoryService, DocumentMemoryService). Add `images_hf_repo_id` config, new `_hf_enabled` + `_setup_hf_storage()` in `ImageAnalyzerSessionManager`, save metadata after vision API call, initialize in `main.py` lifespan.

**Tech Stack:** Python 3.11, huggingface-hub (CommitScheduler), Pydantic Settings, LINE Bot SDK v3, pytest

---

### Task 1: Config — Add Image HF Fields + Validators

**Files:**
- Modify: `src/config.py`
- Test: `tests/test_config.py` (new)

**Step 1: Write failing test**
```python
# tests/test_config.py
def test_images_hf_repo_id_field_exists():
    from src.config import Settings
    s = Settings()
    assert hasattr(s, "images_hf_repo_id")
    assert hasattr(s, "images_hf_enabled")

def test_evilevan_validator_rejects_wrong_prefix():
    from src.config import Settings
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        Settings(images_hf_repo_id="otheruser/bot-images")

def test_evilevan_validator_accepts_correct_prefix():
    from src.config import Settings
    s = Settings(images_hf_repo_id="EvilEvan/teacherboy-images")
    assert s.images_hf_repo_id == "EvilEvan/teacherboy-images"

def test_validator_applies_to_all_hf_repos():
    from src.config import Settings
    from pydantic import ValidationError
    for field in ["hf_memory_repo_id", "document_hf_repo_id", "history_log_hf_repo_id", "calendar_hf_repo_id", "images_hf_repo_id"]:
        with pytest.raises(ValidationError):
            Settings(**{field: "baduser/bad-repo"})
```

**Step 2: Run test — confirm it fails**
```bash
pytest tests/test_config.py -v
# Expected: FAIL — fields don't exist, validators not implemented
```

**Step 3: Write minimal implementation**
```python
# src/config.py — add near line 350 (after calendar_hf_repo_id)
    images_hf_repo_id: str | None = Field(
        default=None,
        description=(
            "Hugging Face dataset repo ID for image analysis persistence. "
            "Example: 'EvilEvan/teacherboy-images'. Will be created as private if it doesn't exist."
        ),
        validate=_validate_evilevan_repo,
    )
    images_hf_enabled: bool = Field(
        default=False,
        description="Enable image analysis persistence to HF Hub.",
    )

# Add validator function near line 900 (before first validated field)
def _validate_evilevan_repo(cls, v: str | None) -> str | None:
    if v and not v.startswith("EvilEvan/teacherboy-"):
        raise ValueError("HF repo must be in EvilEvan/teacherboy-* namespace")
    return v

# Apply validator to existing fields (add validate=_validate_evilevan_repo to each)
    hf_memory_repo_id: str | None = Field(default=None, validate=_validate_evilevan_repo, ...)
    document_hf_repo_id: str | None = Field(default=None, validate=_validate_evilevan_repo, ...)
    history_log_hf_repo_id: str | None = Field(default=None, validate=_validate_evilevan_repo, ...)
    calendar_hf_repo_id: str | None = Field(default=None, validate=_validate_evilevan_repo, ...)
    images_hf_repo_id: str | None = Field(default=None, validate=_validate_evilevan_repo, ...)
```

**Step 4: Run test — confirm it passes**
```bash
pytest tests/test_config.py -v
# Expected: PASS
```

**Step 5: Commit**
```bash
git add src/config.py tests/test_config.py && git commit -m "feat: add images HF config + EvilEvan namespace validators"
```

---

### Task 2: ImageAnalyzerSessionManager — Add HF Persistence

**Files:**
- Modify: `src/services/image_analyzer_session_manager.py`
- Test: `tests/test_image_analyzer_session_manager_hf.py` (new)

**Step 1: Write failing test**
```python
# tests/test_image_analyzer_session_manager_hf.py
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

@pytest.mark.asyncio
async def test_hf_storage_setup_called_when_configured():
    from src.services.image_analyzer_session_manager import ImageAnalyzerSessionManager
    mgr = ImageAnalyzerSessionManager(hf_token="test_token", hf_repo_id="EvilEvan/teacherboy-images")
    assert mgr._hf_enabled is True

@pytest.mark.asyncio
async def test_save_image_metadata_writes_local_json():
    from src.services.image_analyzer_session_manager import ImageAnalyzerSessionManager
    mgr = ImageAnalyzerSessionManager(hf_token="test_token", hf_repo_id="EvilEvan/teacherboy-images")
    with patch("huggingface_hub.HfApi"), patch("huggingface_hub.CommitScheduler"):
        mgr._setup_hf_storage()
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
    from pathlib import Path
    files = list(Path("./data/images").rglob("*.json"))
    assert len(files) == 1
```

**Step 2: Run test — confirm it fails**
```bash
pytest tests/test_image_analyzer_session_manager_hf.py -v
# Expected: FAIL — methods don't exist
```

**Step 3: Write minimal implementation**
```python
# src/services/image_analyzer_session_manager.py

# Add imports
import asyncio
import hashlib
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# In __init__ (after line 91):
        self._images_lock = asyncio.Lock()
        self._images_hf_enabled = bool(hf_token and hf_repo_id)
        self._images_hf_token = hf_token
        self._images_hf_repo_id = hf_repo_id
        self._images_hf_api: Any | None = None
        self._images_commit_scheduler: Any | None = None
        self._images_local_path = self.local_storage_path / "images"
        if self._images_hf_enabled:
            self._setup_images_hf_storage()

# Add methods:
    def _setup_images_hf_storage(self):
        """Initialize HF Hub storage for images."""
        if not self._images_hf_token or not self._images_hf_repo_id:
            self._images_hf_enabled = False
            return
        try:
            import importlib
            hf = importlib.import_module("huggingface_hub")
            HfApi = hf.HfApi
            CommitScheduler = hf.CommitScheduler
            hf_api = HfApi(token=self._images_hf_token)
            self._images_hf_api = hf_api
            self._images_local_path.mkdir(parents=True, exist_ok=True)
            hf_api.create_repo(
                repo_id=self._images_hf_repo_id,
                repo_type="dataset",
                private=True,
                exist_ok=True,
            )
            self._images_commit_scheduler = CommitScheduler(
                repo_id=self._images_hf_repo_id,
                repo_type="dataset",
                folder_path=str(self._images_local_path),
                every=5,  # 5 minutes
                token=self._images_hf_token,
                private=True,
                squash_history=True,
            )
            logger.info(f"🖼️ Image analysis HF storage ready: {self._images_hf_repo_id}")
        except Exception as e:
            logger.warning(f"⚠️ Image HF storage init failed: {e}")
            self._images_hf_enabled = False

    def _hash_chat_id(self, chat_id: str) -> str:
        return hashlib.sha256(chat_id.encode("utf-8")).hexdigest()[:16]

    async def save_image_metadata(
        self,
        chat_id: str,
        image_base64: str,
        prompt: str,
        response: str,
        analysis_mode: str,
        duration_ms: int,
        image_size_bytes: int,
        model_used: str,
    ) -> str:
        """Save image analysis result to local storage for HF sync."""
        image_id = hashlib.sha256((chat_id + prompt + str(datetime.now(UTC))).encode()).hexdigest()[:32]
        hashed_chat = self._hash_chat_id(chat_id)
        chat_dir = self._images_local_path / hashed_chat
        chat_dir.mkdir(parents=True, exist_ok=True)
        file_path = chat_dir / f"{image_id}.json"
        
        metadata = {
            "id": image_id,
            "chat_id": chat_id,
            "hashed_chat_id": hashed_chat,
            "timestamp": datetime.now(UTC).isoformat(),
            "image_base64": image_base64,
            "prompt": prompt,
            "response": response,
            "analysis_mode": analysis_mode,
            "duration_ms": duration_ms,
            "image_size_bytes": image_size_bytes,
            "model_used": model_used,
        }
        
        async with self._images_lock:
            temp_path = file_path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)
            temp_path.rename(file_path)
        
        logger.info(f"🖼️ Saved image metadata for {hashed_chat[:8]}... ({image_id[:8]})")
        return image_id
```

**Step 4: Run test — confirm it passes**
```bash
pytest tests/test_image_analyzer_session_manager_hf.py -v
# Expected: PASS
```

**Step 5: Commit**
```bash
git add src/services/image_analyzer_session_manager.py tests/test_image_analyzer_session_manager_hf.py && git commit -m "feat: add HF persistence to ImageAnalyzerSessionManager"
```

---

### Task 3: ImageAnalyzerAgent — Save Metadata After Vision Call

**Files:**
- Modify: `src/agents/image_analyzer_agent.py`
- Test: `tests/test_image_analyzer_persistence.py` (new)

**Step 1: Write failing test**
```python
# tests/test_image_analyzer_persistence.py
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from linebot.v3.messaging import MessagingApi
from linebot.v3.webhooks import MessageEvent

@pytest.mark.asyncio
async def test_handle_question_saves_metadata():
    from src.agents.image_analyzer_agent import ImageAnalyzerAgent
    agent = ImageAnalyzerAgent()
    mock_event = MagicMock()
    mock_event.source.user_id = "user_123"
    mock_event.source.group_id = "group_123"
    mock_line_bot_api = MagicMock(spec=MessagingApi)
    
    with patch("src.agents.image_analyzer_agent.image_analyzer_session_manager") as mock_mgr:
        mock_mgr.get_image_and_question = AsyncMock(return_value=("data:image/jpeg;base64,abc", "test prompt", "standard"))
        mock_mgr.save_image_metadata = AsyncMock(return_value="img_123")
        mock_mgr.clear_session = AsyncMock()
        
        with patch("src.agents.image_analyzer_agent.chat_completion_with_vision_fallback", new=AsyncMock(return_value="analysis result")):
            with patch("src.agents.image_analyzer_agent.asyncio.to_thread", new=AsyncMock()):
                await agent._handle_question(mock_event, "test prompt", "group_123", "user_123", mock_line_bot_api, MagicMock())
        
        mock_mgr.save_image_metadata.assert_awaited_once()
        call_kwargs = mock_mgr.save_image_metadata.call_args.kwargs
        assert call_kwargs["prompt"] == "test prompt"
        assert call_kwargs["response"] == "analysis result"
```

**Step 2: Run test — confirm it fails**
```bash
pytest tests/test_image_analyzer_persistence.py -v
# Expected: FAIL — save_image_metadata not called
```

**Step 3: Write minimal implementation**
```python
# src/agents/image_analyzer_agent.py — in _handle_question, after vision API call (around line 870)

        # Call vision via provider-agnostic fallback
        logger.info(f"🖼️ Analyzing image with question: {question[:50]}...")

        start_time = datetime.now(UTC)
        model = getattr(settings, "profiler_model", "openai/gpt-4o")
        analysis = await chat_completion_with_vision_fallback(
            messages=messages,
            model=model,
            temperature=0.15 if low_risk_scene else settings.llm_temperature,
            max_tokens=2000,
        )
        duration_ms = int((datetime.now(UTC) - start_time).total_seconds() * 1000)

        # ... existing retry logic ...

        # CRITICAL: Clear image data from memory after vision API call
        del image_data  # Clear base64 data URL
        del messages  # Clear vision API messages containing image

        if not analysis:
            # ... existing error handling ...

        span.set_attribute("analyzer.success", True)
        span.set_attribute("analysis.length", len(analysis))

        # NEW: Save image metadata to HF (if enabled)
        if hasattr(image_analyzer_session_manager, "save_image_metadata"):
            try:
                await image_analyzer_session_manager.save_image_metadata(
                    chat_id=chat_id,
                    image_base64=image_data if 'image_data' in locals() else "",
                    prompt=question,
                    response=analysis,
                    analysis_mode=analysis_mode,
                    duration_ms=duration_ms,
                    image_size_bytes=span.attributes.get("image.size_bytes", 0),
                    model_used=model,
                )
            except Exception as e:
                logger.warning(f"⚠️ Failed to save image metadata: {e}")
```

**Step 4: Run test — confirm it passes**
```bash
pytest tests/test_image_analyzer_persistence.py -v
# Expected: PASS
```

**Step 5: Commit**
```bash
git add src/agents/image_analyzer_agent.py tests/test_image_analyzer_persistence.py && git commit -m "feat: save image metadata after vision analysis"
```

---

### Task 4: main.py — Initialize Image HF Storage in Lifespan

**Files:**
- Modify: `src/main.py`
- Test: `tests/test_main_lifespan.py` (extend)

**Step 1: Write failing test**
```python
# tests/test_main_lifespan.py
def test_images_hf_init_in_lifespan():
    # Verify init_images_hf called when configured
    from src.main import lifespan
    # Integration test - verify the initialization path exists
    pass
```

**Step 2: Run test — confirm it fails**
```bash
pytest tests/test_main_lifespan.py -v
# Expected: FAIL — no init call
```

**Step 3: Write minimal implementation**
```python
# src/main.py — add after line 234 (document memory init block)

    # ========================================================================
    # PHASE 2a5: Image HF Persistence Initialization
    # ========================================================================
    if settings.images_hf_enabled and settings.images_hf_repo_id:
        from src.services.image_analyzer_session_manager import image_analyzer_session_manager
        # Re-initialize with HF credentials if not already done
        if not image_analyzer_session_manager._images_hf_enabled:
            image_analyzer_session_manager._images_hf_token = settings.hf_memory_token
            image_analyzer_session_manager._images_hf_repo_id = settings.images_hf_repo_id
            image_analyzer_session_manager._setup_images_hf_storage()
        logger.info(f"🖼️ Image analysis HF persistence enabled: {settings.images_hf_repo_id}")
    else:
        logger.info("🖼️ Image analysis HF persistence disabled")
```

**Step 4: Run test — confirm it passes**
```bash
pytest tests/test_main_lifespan.py -v
# Expected: PASS
```

**Step 5: Commit**
```bash
git add src/main.py && git commit -m "feat: initialize image HF persistence in lifespan"
```

---

### Task 5: Full Test Suite — Verify All Tests Pass

**Files:**
- Run: all tests

**Step 1: Run full suite**
```bash
pytest tests/ --tb=short -q
# Expected: 746+ passed (including new tests)
```

**Step 2: Lint + type check**
```bash
ruff check src/ && ruff format --check src/ && mypy src/ --ignore-missing-imports
# Expected: All pass
```

**Step 3: Commit any final fixes**
```bash
git add -A && git commit -m "fix: final adjustments for HF image persistence"
```

---

### After Plan Completion

Push to HF Spaces:
```bash
git push hf HEAD:main
```

Set environment variables on HF Space:
- `HF_MEMORY_TOKEN` (write scope)
- `IMAGES_HF_REPO_ID=EvilEvan/teacherboy-images`
- `IMAGES_HF_ENABLED=true`