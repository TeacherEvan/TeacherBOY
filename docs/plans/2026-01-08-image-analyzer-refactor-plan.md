# Image Analyzer Agent Refactor Implementation Plan

> **For implementer:** Use TDD throughout. Write failing test first. Watch it fail. Then implement.

**Goal:** Refactor `ImageAnalyzerAgent` by splitting its responsibilities into smaller, more manageable classes and creating a shared `VisionBaseAgent` for common vision-related functionalities with `ProfilerAgent`.

**Architecture:**
Introduce `VisionBaseAgent` to encapsulate common image downloading, base64 encoding, and vision message building logic. Create dedicated handler classes (e.g., `TriggerHandler`, `ImageHandler`, `QuestionHandler`, `CalendarConfirmationHandler`) to manage specific states and actions within the `ImageAnalyzerAgent`'s flow. The `ImageAnalyzerAgent` will act as an orchestrator, delegating to these new handler classes.

**Tech Stack:** Python 3.11+, FastAPI, LINE Bot SDK v3, Pydantic, mypy for type hints.

---

### Task 1: Create `VisionBaseAgent`

**Files:**
- Create: `src/agents/vision_base_agent.py`
- Modify: `src/agents/image_analyzer_agent.py`
- Modify: `src/agents/profiler_agent.py`
- Test: `tests/test_vision_base_agent.py` (new)

**Step 1: Write the failing test for `VisionBaseAgent`**
Create `tests/test_vision_base_agent.py` with tests for image download, base64 conversion, and vision message building.

```python
# tests/test_vision_base_agent.py
import asyncio
import base64
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from linebot.v3.messaging import Configuration, MessagingApiBlob
from linebot.v3.webhooks import MessageEvent, Source

from src.agents.vision_base_agent import VisionBaseAgent
from src.config import settings

class TestVisionBaseAgent:
    @pytest.fixture
    def mock_line_api_client(self):
        with patch("linebot.v3.messaging.ApiClient") as mock_api_client_class:
            mock_api_client = MagicMock()
            mock_api_client_class.return_value.__enter__.return_value = mock_api_client
            yield mock_api_client

    @pytest.fixture
    def vision_base_agent(self, mock_line_api_client):
        # VisionBaseAgent needs a MessagingApiBlob instance, mock it
        mock_messaging_api_blob = MagicMock(spec=MessagingApiBlob)
        return VisionBaseAgent(messaging_api_blob=mock_messaging_api_blob)

    @pytest.fixture
    def mock_event(self):
        event = MagicMock(spec=MessageEvent)
        event.source = MagicMock(spec=Source)
        event.source.user_id = "test_user"
        event.source.group_id = None
        event.source.room_id = None
        return event

    def test_get_chat_id_user(self, vision_base_agent, mock_event):
        chat_id = vision_base_agent._get_chat_id(mock_event)
        assert chat_id == "user_test_user"

    def test_get_chat_id_group(self, vision_base_agent, mock_event):
        mock_event.source.user_id = None
        mock_event.source.group_id = "test_group"
        chat_id = vision_base_agent._get_chat_id(mock_event)
        assert chat_id == "group_test_group"

    def test_get_chat_id_room(self, vision_base_agent, mock_event):
        mock_event.source.user_id = None
        mock_event.source.room_id = "test_room"
        chat_id = vision_base_agent._get_chat_id(mock_event)
        assert chat_id == "room_test_room"

    @pytest.mark.asyncio
    async def test_download_image_success(self, vision_base_agent, mock_line_api_client):
        mock_message_id = "test_message_id"
        mock_image_bytes = b"fake_image_bytes"
        
        # Configure the mock to return bytes
        mock_blob_api = vision_base_agent.blob_api
        mock_blob_api.get_message_content = AsyncMock(return_value=mock_image_bytes)

        # Patch settings for LINE_CHANNEL_ACCESS_TOKEN
        with patch.object(settings, "line_channel_access_token", "fake_token"):
            downloaded_bytes = await vision_base_agent._download_image(mock_message_id)

        assert downloaded_bytes == mock_image_bytes
        mock_blob_api.get_message_content.assert_called_once_with(mock_message_id)

    @pytest.mark.asyncio
    async def test_download_image_failure(self, vision_base_agent, mock_line_api_client):
        mock_message_id = "test_message_id"
        
        # Configure the mock to raise an exception
        mock_blob_api = vision_base_agent.blob_api
        mock_blob_api.get_message_content = AsyncMock(side_effect=Exception("Download error"))

        with patch.object(settings, "line_channel_access_token", "fake_token"):
            downloaded_bytes = await vision_base_agent._download_image(mock_message_id)

        assert downloaded_bytes is None
        mock_blob_api.get_message_content.assert_called_once_with(mock_message_id)
    
    def test_build_vision_message_standard(self, vision_base_agent):
        image_data_url = "data:image/jpeg;base64,abc"
        question = "What is this image about?"
        messages = vision_base_agent._build_vision_message(image_data_url, question, scene_mode="standard")
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert "Examine this image and answer my question" in messages[1]["content"][0]["text"]
        assert messages[1]["content"][1]["image_url"]["url"] == image_data_url

    def test_build_vision_message_literal_scene(self, vision_base_agent):
        image_data_url = "data:image/jpeg;base64,abc"
        question = "Tell me about the baby"
        messages = vision_base_agent._build_vision_message(image_data_url, question, scene_mode="literal")
        assert "Stay extremely literal and calm" in messages[0]["content"]

    @patch("src.services.github_models_service.github_models_service")
    @patch("src.services.openrouter_service.openrouter_service")
    def test_get_vision_error_detail(self, mock_openrouter, mock_github, vision_base_agent):
        mock_github.get_last_error.return_value = (400, "Bad Request", "github_model")
        mock_openrouter.get_last_error.return_value = None

        status, detail, model = vision_base_agent._get_vision_error_detail()
        assert status == 400
        assert detail == "Bad Request"
        assert model == "github_model"

        mock_github.get_last_error.return_value = None
        mock_openrouter.get_last_error.return_value = (401, "Unauthorized", "openrouter_model")
        status, detail, model = vision_base_agent._get_vision_error_detail()
        assert status == 401
        assert detail == "Unauthorized"
        assert model == "openrouter_model"

        mock_github.get_last_error.return_value = None
        mock_openrouter.get_last_error.return_value = None
        status, detail, model = vision_base_agent._get_vision_error_detail()
        assert status is None
        assert detail is None
        assert model is None
```

**Step 2: Run test — confirm it fails**
Command: `pytest tests/test_vision_base_agent.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.agents.vision_base_agent'`

**Step 3: Write minimal implementation for `VisionBaseAgent`**
Create `src/agents/vision_base_agent.py` and move common methods.

```python
# src/agents/vision_base_agent.py
import asyncio
import base64
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
import re

from linebot.v3.messaging import ApiClient, Configuration, MessagingApiBlob
from linebot.v3.webhooks import MessageEvent

from src.config import settings
from src.services.github_models_service import github_models_service
from src.services.openrouter_service import openrouter_service
from src.utils.tracing import get_tracer

from .base_agent import BaseAgent

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)

class VisionBaseAgent(BaseAgent):
    def __init__(self, name: str, description: str, messaging_api_blob: MessagingApiBlob | None = None):
        super().__init__(name=name, description=description)
        self.blob_api = messaging_api_blob

    def _get_chat_id(self, event: MessageEvent) -> str:
        """Extract chat ID from event."""
        if event.source and hasattr(event.source, "group_id"):
            group_id = getattr(event.source, "group_id", None)
            if group_id:
                return f"group_{group_id}"
        if event.source and hasattr(event.source, "room_id"):
            room_id = getattr(event.source, "room_id", None)
            if room_id:
                return f"room_{room_id}"
        if event.source:
            user_id = getattr(event.source, "user_id", "unknown")
            return f"user_{user_id}"
        return "user_unknown"

    async def _download_image(self, message_id: str) -> bytes | None:
        """Download image content from LINE servers."""
        try:
            if not self.blob_api:
                logger.error("MessagingApiBlob client not initialized for image download.")
                return None

            response = await asyncio.to_thread(self.blob_api.get_message_content, message_id)

            if response is None:
                logger.warning("❌ Response is None from LINE API")
                return None

            if isinstance(response, bytes):
                return response
            elif isinstance(response, bytearray):
                return bytes(response)
            elif hasattr(response, "read") and callable(getattr(response, "read", None)):
                return response.read()
            else:
                chunks = []
                try:
                    for chunk in response: # type: ignore[union-attr]
                        chunks.append(chunk)
                    return b"".join(chunks)
                except TypeError:
                    logger.error(f"❌ Unexpected response type: {type(response)}")
                    return None

        except Exception as e:
            logger.error(f"❌ Failed to download image {message_id}: {e}", exc_info=True)
            return None

    def _build_vision_message(self, image_data_url: str, question: str, scene_mode: str = "standard") -> list:
        """Build the vision API message structure."""
        bangkok_tz = ZoneInfo("Asia/Bangkok")
        today = datetime.now(bangkok_tz)
        today_str = today.strftime("%B %d, %Y")
        current_year = today.year
        question_lower = (question or "").lower().strip()

        neutral_scene_terms = [
            "baby", "newborn", "breastfeed", "breast feeding", "breastfeeding",
            "family", "mother", "father", "child", "medical", "hospital",
            "food", "menu", "sign", "document", "receipt", "package",
            "product", "pet", "home", "household", "room", "care",
        ]

        extra_conservative_instruction = ""
        if scene_mode == "literal" or any(term in question_lower for term in neutral_scene_terms):
            extra_conservative_instruction = (
                "This looks like a normal everyday scene. "
                "Stay extremely literal and calm; do not sexualize, sensationalize, or assume hidden intent. "
                "If the image is simply caregiving, feeding, family, medical, or household context, describe it plainly. "
            )

        system_prompt = (
            "You are Ms. Green, a polite and observant assistant. "
            "You speak with calm clarity and practical warmth. "
            "When analyzing images, be maximally literal, neutral, and conservative. "
            "Prefer plain description over speculation; if something is ambiguous, say so. "
            "Treat ordinary family, caregiving, infant-feeding, medical, pet, food, document, and household scenes as normal unless the user asks otherwise. "
            "Do not overreact to benign content; keep a steady, careful tone. "
            f"{extra_conservative_instruction}"
            "For menus, signs, or text: translate and explain if in another language. "
            "For products or items: describe what you see and provide recommendations if asked.\n\n"
            f"TODAY'S DATE: {today_str} (Year: {current_year})\n\n"
            "IMPORTANT: If you detect any dates, deadlines, events, or schedules in the image, "
            "always include a section at the end of your response with the following format:\n"
            "---DATES_DETECTED---\n"
            '[''{"date": "2026-01-15", "title": "Event title", "description": "Brief description"} ]\n'
            "---END_DATES---\n"
            f"Use ISO format (YYYY-MM-DD) for dates. ALWAYS use the actual year number (e.g., {current_year}), never 'YYYY' as a placeholder. "
            f"If the year is not specified in the image, use {current_year} for dates that haven't passed yet, or {current_year + 1} for dates earlier in the year that have already passed. "
            "Only include this section if you actually find date-related information in the image."
        )

        return [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"Examine this image and answer my question:\n\n{question}",
                    },
                    {"type": "image_url", "image_url": {"url": image_data_url}},
                ],
            },
        ]

    def _get_vision_error_detail(self) -> tuple[int | None, str | None, str | None]:
        """Collect the most recent vision API error detail."""
        for svc in (github_models_service, openrouter_service):
            try:
                detail = svc.get_last_error()
            except AttributeError:
                continue
            if detail and detail[1]:
                return detail
        return (None, None, None)
```

**Step 4: Run test — confirm it passes**
Command: `pytest tests/test_vision_base_agent.py -v`
Expected: PASS

**Step 5: Commit**
`git add src/agents/vision_base_agent.py tests/test_vision_base_agent.py && git commit -m "feat: implement VisionBaseAgent"`

---

### Task 2: Update `ImageAnalyzerAgent` to use `VisionBaseAgent`

**Files:**
- Modify: `src/agents/image_analyzer_agent.py`

**Step 1: Write the failing test for `ImageAnalyzerAgent` inheritance**
Modify an existing test in `tests/test_image_analyzer_calendar.py` or `tests/test_image_analyzer_agent.py` to check that `ImageAnalyzerAgent` now inherits from `VisionBaseAgent` and uses its methods for image downloading and `_get_chat_id`. (We'll add `tests/test_image_analyzer_agent.py` later for specific tests for this agent). For now, let's create a minimal test in `tests/test_image_analyzer_agent.py` (which currently doesn't exist).

```python
# tests/test_image_analyzer_agent.py
import pytest
from unittest.mock import MagicMock, patch
from linebot.v3.messaging import MessagingApiBlob
from src.agents.image_analyzer_agent import ImageAnalyzerAgent
from src.agents.vision_base_agent import VisionBaseAgent

class TestImageAnalyzerAgentBase:
    @pytest.fixture
    def mock_messaging_api_blob(self):
        return MagicMock(spec=MessagingApiBlob)

    @pytest.fixture
    def image_analyzer_agent(self, mock_messaging_api_blob):
        return ImageAnalyzerAgent(messaging_api_blob=mock_messaging_api_blob)

    def test_inherits_from_vision_base_agent(self, image_analyzer_agent):
        assert isinstance(image_analyzer_agent, VisionBaseAgent)

    def test_uses_vision_base_agent_init(self, image_analyzer_agent, mock_messaging_api_blob):
        # Verify that VisionBaseAgent's __init__ was called with correct args
        # This is a bit indirect as BaseAgent also takes name, description
        # but we can check if blob_api is set
        assert image_analyzer_agent.blob_api is mock_messaging_api_blob
```

**Step 2: Run test — confirm it fails**
Command: `pytest tests/test_image_analyzer_agent.py -v`
Expected: FAIL - `ImageAnalyzerAgent` does not currently accept `messaging_api_blob` in its `__init__` and does not inherit `VisionBaseAgent`.

**Step 3: Write minimal implementation for `ImageAnalyzerAgent` inheritance**
Modify `src/agents/image_analyzer_agent.py`.

```python
# src/agents/image_analyzer_agent.py (changes only)
# ...
from linebot.v3.messaging import (
    # ...
    MessagingApiBlob, # Add this import
)
# ...
from .base_agent import BaseAgent
from .vision_base_agent import VisionBaseAgent # New import

# ...

class ImageAnalyzerAgent(VisionBaseAgent): # Change base class
    # ...
    def __init__(self, http_client=None, messaging_api_blob: MessagingApiBlob | None = None): # Add messaging_api_blob
        """
        Initialize ImageAnalyzerAgent.

        Args:
            http_client: Shared HTTP client
            messaging_api_blob: LINE API blob client for downloading images
        """
        super().__init__(
            name="ImageAnalyzerAgent",
            description="General purpose image Q&A using vision AI",
            messaging_api_blob=messaging_api_blob # Pass to base
        )
        self.http_client = http_client
        # Remove self.blob_api = messaging_api_blob as it's handled by base class
        # ... other unchanged init logic
```
Also, remove the `_get_chat_id`, `_download_image`, `_build_vision_message`, `_get_vision_error_detail` methods from `ImageAnalyzerAgent` as they are now in `VisionBaseAgent`. Update calls within `ImageAnalyzerAgent` to `self._download_image` etc.

**Step 4: Run test — confirm it passes**
Command: `pytest tests/test_image_analyzer_agent.py -v`
Expected: PASS

**Step 5: Commit**
`git add src/agents/image_analyzer_agent.py tests/test_image_analyzer_agent.py && git commit -m "refactor: ImageAnalyzerAgent inherits VisionBaseAgent"`

---

### Task 3: Update `ProfilerAgent` to use `VisionBaseAgent`

**Files:**
- Modify: `src/agents/profiler_agent.py`

**Step 1: Write the failing test for `ProfilerAgent` inheritance**
Create `tests/test_profiler_agent.py` (if it doesn't exist) with minimal tests to check inheritance and `blob_api` setting.

```python
# tests/test_profiler_agent.py
import pytest
from unittest.mock import MagicMock, patch
from linebot.v3.messaging import MessagingApiBlob
from src.agents.profiler_agent import ProfilerAgent
from src.agents.vision_base_agent import VisionBaseAgent

class TestProfilerAgentBase:
    @pytest.fixture
    def mock_messaging_api_blob(self):
        return MagicMock(spec=MessagingApiBlob)

    @pytest.fixture
    def profiler_agent(self, mock_messaging_api_blob):
        return ProfilerAgent(messaging_api_blob=mock_messaging_api_blob)

    def test_inherits_from_vision_base_agent(self, profiler_agent):
        assert isinstance(profiler_agent, VisionBaseAgent)

    def test_uses_vision_base_agent_init(self, profiler_agent, mock_messaging_api_blob):
        assert profiler_agent.blob_api is mock_messaging_api_blob
```

**Step 2: Run test — confirm it fails**
Command: `pytest tests/test_profiler_agent.py -v`
Expected: FAIL - `ProfilerAgent` does not currently inherit `VisionBaseAgent`.

**Step 3: Write minimal implementation for `ProfilerAgent` inheritance**
Modify `src/agents/profiler_agent.py`.

```python
# src/agents/profiler_agent.py (changes only)
# ...
from linebot.v3.messaging import (
    # ...
    MessagingApiBlob, # Ensure this is imported
)
# ...
from .base_agent import BaseAgent
from .vision_base_agent import VisionBaseAgent # New import

# ...

class ProfilerAgent(VisionBaseAgent): # Change base class
    # ...
    def __init__(self, http_client=None, messaging_api_blob: MessagingApiBlob | None = None):
        """
        Initialize ProfilerAgent.

        Args:
            http_client: Shared HTTP client (not used directly but kept for interface consistency)
            messaging_api_blob: LINE API blob client for downloading images
        """
        super().__init__(
            name="ProfilerAgent",
            description="Psychological profiling from photos using AI vision",
            messaging_api_blob=messaging_api_blob # Pass to base
        )
        self.http_client = http_client
        # Remove self.blob_api = messaging_api_blob as it's handled by base class
```
Also, remove the `_get_chat_id`, `_download_image` (if present) methods from `ProfilerAgent` as they are now in `VisionBaseAgent`. The `_build_vision_message` logic in `ProfilerAgent` is more specialized, so it will remain for now, but `ProfilerAgent` should eventually use `VisionBaseAgent`'s `_get_vision_error_detail`.

**Step 4: Run test — confirm it passes**
Command: `pytest tests/test_profiler_agent.py -v`
Expected: PASS

**Step 5: Commit**
`git add src/agents/profiler_agent.py tests/test_profiler_agent.py && git commit -m "refactor: ProfilerAgent inherits VisionBaseAgent"`

---

I will now write this plan to the file and offer the execution options.
