# Translation Auto-Handoff and Image Consent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore automatic Thai-to-AI translation handoff, suppress likely translation-bot echo replies that arrive in a second language within 2 seconds, and auto-prompt for basic image analysis on every image.

**Architecture:** Keep translation ownership in `TranslationAgent`, but move the new echo-suppression memory into `SessionManager` so the behavior stays chat-scoped and testable. Extend `ImageAnalyzerAgent` and `image_analyzer_session_manager` with a lightweight consent path that stores the latest image, prompts with Yes/No quick replies, and runs a default one-shot summary without touching the existing advanced/admin flows.

**Tech Stack:** Python 3.11, FastAPI, LINE Messaging API v3, pytest, GitHub Models vision

---

## File Structure

- Modify: `src/services/session_manager.py` — add recent-language tracking and a helper that detects a likely cross-language bot echo inside a 2-second window.
- Modify: `src/agents/translation_agent.py` — restore Thai auto-handoff when no session is active and consult the new suppression helper before translating.
- Modify: `src/services/image_analyzer_session_manager.py` — add a consent state for “Would you like me to Analyze this image?” and retain the uploaded image for the default flow.
- Modify: `src/agents/image_analyzer_agent.py` — prompt on unsolicited image uploads, handle Yes/No consent replies, and run a default one-shot analysis on Yes.
- Modify: `tests/test_session_manager.py` — cover the new recent-language suppression behavior.
- Create: `tests/test_translation_agent_auto_handoff.py` — cover Thai auto-handoff and second-message suppression at the translation agent boundary.
- Create: `tests/test_image_analyzer_auto_prompt.py` — cover image consent prompting and default-analysis replies.

### Task 1: Add cross-language echo suppression primitives

**Files:**
- Modify: `src/services/session_manager.py`
- Test: `tests/test_session_manager.py`

- [ ] **Step 1: Write the failing tests**

```python
from datetime import timedelta

from src.services.session_manager import SessionManager


def test_marks_second_cross_language_message_within_two_seconds_as_echo():
    manager = SessionManager()

    assert manager.should_ignore_cross_language_echo("group_123", "สวัสดี", now_offset_seconds=0) is False
    assert manager.should_ignore_cross_language_echo("group_123", "hello", now_offset_seconds=1) is True


def test_keeps_first_message_when_order_is_reversed():
    manager = SessionManager()

    assert manager.should_ignore_cross_language_echo("group_123", "hello", now_offset_seconds=0) is False
    assert manager.should_ignore_cross_language_echo("group_123", "สวัสดี", now_offset_seconds=1) is True


def test_does_not_ignore_after_two_second_window():
    manager = SessionManager()

    assert manager.should_ignore_cross_language_echo("group_123", "สวัสดี", now_offset_seconds=0) is False
    assert manager.should_ignore_cross_language_echo("group_123", "hello", now_offset_seconds=3) is False


def test_does_not_ignore_same_language_messages():
    manager = SessionManager()

    assert manager.should_ignore_cross_language_echo("group_123", "hello", now_offset_seconds=0) is False
    assert manager.should_ignore_cross_language_echo("group_123", "how are you", now_offset_seconds=1) is False
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_session_manager.py -k cross_language -v`

Expected: FAIL with `AttributeError: 'SessionManager' object has no attribute 'should_ignore_cross_language_echo'`

- [ ] **Step 3: Write the minimal implementation**

```python
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple


class SessionManager:
    def __init__(
        self,
        dedup_window_seconds: int = 60,
        max_history_size: int = 50,
        default_sleep_hours: int = 24,
        echo_window_seconds: int = 2,
    ):
        self._recent_language_messages: Dict[str, Tuple[str, datetime]] = {}
        self._echo_window_seconds = echo_window_seconds

    def _detect_message_language(self, text: str) -> str:
        return "th" if bool(re.search(r"[\u0E00-\u0E7F]", text)) else "en"

    def should_ignore_cross_language_echo(
        self,
        chat_id: str,
        text: str,
        *,
        now: Optional[datetime] = None,
        now_offset_seconds: Optional[int] = None,
    ) -> bool:
        current_time = now or datetime.now()
        if now_offset_seconds is not None:
            current_time = datetime.now() + timedelta(seconds=now_offset_seconds)

        language = self._detect_message_language(text)
        previous = self._recent_language_messages.get(chat_id)
        self._recent_language_messages[chat_id] = (language, current_time)

        if previous is None:
            return False

        previous_language, previous_time = previous
        age_seconds = (current_time - previous_time).total_seconds()
        return previous_language != language and age_seconds < self._echo_window_seconds
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_session_manager.py -k cross_language -v`

Expected: PASS for the 4 new cross-language tests

- [ ] **Step 5: Commit**

```bash
git add src/services/session_manager.py tests/test_session_manager.py
git commit -m "feat: add cross-language echo suppression"
```

### Task 2: Restore Thai auto-handoff in the translation agent

**Files:**
- Modify: `src/agents/translation_agent.py`
- Create: `tests/test_translation_agent_auto_handoff.py`

- [ ] **Step 1: Write the failing tests**

```python
import pytest
from unittest.mock import AsyncMock

from src.agents.translation_agent import TranslationAgent
from src.services.session_manager import session_manager


@pytest.mark.asyncio
async def test_should_handle_thai_when_session_is_inactive(fake_text_event):
    agent = TranslationAgent(ai_translation_service=AsyncMock())
    chat_id = agent._get_chat_id(fake_text_event("สวัสดี"))
    session_manager.end_session(chat_id)

    assert await agent.should_handle(fake_text_event("สวัสดี"), "สวัสดี") is True


@pytest.mark.asyncio
async def test_handle_ignores_second_cross_language_message(fake_text_event, fake_line_bot_api):
    translation_service = AsyncMock()
    translation_service.translate.return_value.text = "hello"
    agent = TranslationAgent(ai_translation_service=translation_service)

    first_event = fake_text_event("สวัสดี")
    second_event = fake_text_event("hello")

    assert await agent.handle(first_event, "สวัสดี", fake_line_bot_api) is True
    fake_line_bot_api.reply_message.reset_mock()

    assert await agent.handle(second_event, "hello", fake_line_bot_api) is True
    fake_line_bot_api.reply_message.assert_not_called()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_translation_agent_auto_handoff.py -v`

Expected: FAIL because `should_handle()` currently returns `False` for Thai when no session is active, and the second message still gets translated.

- [ ] **Step 3: Write the minimal implementation**

```python
    async def should_handle(self, event: MessageEvent, text: str) -> bool:
        chat_id = self._get_chat_id(event)

        if self.is_wake_command(text):
            return True

        if self.is_sleep_command(text):
            ...

        if session_manager.is_sleeping(chat_id):
            user_id = getattr(event.source, "user_id", None) if event.source else None
            if privilege_service.is_admin(user_id) and self.contains_thai(text):
                return True
            return False

        if self.is_news_trigger(text) or self.is_special_news_command(text):
            return False

        if self.contains_thai(text):
            return True

        return session_manager.is_session_active(chat_id)

    async def handle(
        self, event: MessageEvent, text: str, line_bot_api: MessagingApi
    ) -> bool:
        chat_id = self._get_chat_id(event)

        if session_manager.should_ignore_cross_language_echo(chat_id, text):
            logger.info("🔁 Ignoring likely translation-bot echo in chat %s", chat_id)
            return True

        if self.contains_thai(text) and not session_manager.is_session_active(chat_id):
            session_manager.start_session(chat_id, user_id or "unknown")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_translation_agent_auto_handoff.py tests/test_session_manager.py -k "auto_handoff or cross_language" -v`

Expected: PASS for the new translation-agent and session-manager tests

- [ ] **Step 5: Commit**

```bash
git add src/agents/translation_agent.py tests/test_translation_agent_auto_handoff.py src/services/session_manager.py tests/test_session_manager.py
git commit -m "fix: restore thai auto handoff"
```

### Task 3: Add image auto-consent session state

**Files:**
- Modify: `src/services/image_analyzer_session_manager.py`
- Create: `tests/test_image_analyzer_auto_prompt.py`

- [ ] **Step 1: Write the failing tests**

```python
from src.services.image_analyzer_session_manager import image_analyzer_session_manager


def test_start_auto_prompt_tracks_pending_image_consent():
    chat_id = "group_123"
    user_id = "user_123"
    image_analyzer_session_manager.start_auto_prompt(chat_id, user_id, "data:image/jpeg;base64,abc")

    assert image_analyzer_session_manager.is_waiting_for_auto_prompt(chat_id, user_id) is True
    assert image_analyzer_session_manager.get_last_image(chat_id) == "data:image/jpeg;base64,abc"


def test_clear_session_removes_auto_prompt_state():
    chat_id = "group_123"
    user_id = "user_123"
    image_analyzer_session_manager.start_auto_prompt(chat_id, user_id, "data:image/jpeg;base64,abc")

    image_analyzer_session_manager.clear_session(chat_id)

    assert image_analyzer_session_manager.is_waiting_for_auto_prompt(chat_id, user_id) is False
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_image_analyzer_auto_prompt.py -v`

Expected: FAIL with missing `start_auto_prompt()` / `is_waiting_for_auto_prompt()` methods

- [ ] **Step 3: Write the minimal implementation**

```python
class SessionState:
    WAITING_FOR_AUTO_PROMPT = "waiting_for_auto_prompt"


class ImageAnalyzerSessionManager:
    def start_auto_prompt(self, chat_id: str, user_id: Optional[str], image_data: str) -> None:
        self._sessions[chat_id] = {
            "user_id": user_id,
            "state": SessionState.WAITING_FOR_AUTO_PROMPT,
            "image_data": image_data,
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
            "analysis_mode": "auto_basic",
        }

    def is_waiting_for_auto_prompt(self, chat_id: str, user_id: Optional[str] = None) -> bool:
        session = self._sessions.get(chat_id)
        if not session:
            return False
        if session.get("state") != SessionState.WAITING_FOR_AUTO_PROMPT:
            return False
        if user_id is not None and session.get("user_id") not in {None, user_id}:
            return False
        return True
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_image_analyzer_auto_prompt.py -v`

Expected: PASS for both auto-prompt session-manager tests

- [ ] **Step 5: Commit**

```bash
git add src/services/image_analyzer_session_manager.py tests/test_image_analyzer_auto_prompt.py
git commit -m "feat: add image auto prompt session state"
```

### Task 4: Prompt on every image and run the default one-shot analysis

**Files:**
- Modify: `src/agents/image_analyzer_agent.py`
- Test: `tests/test_image_analyzer_auto_prompt.py`

- [ ] **Step 1: Write the failing tests**

```python
import pytest
from unittest.mock import AsyncMock

from src.agents.image_analyzer_agent import ImageAnalyzerAgent


@pytest.mark.asyncio
async def test_unsolicited_image_prompts_for_basic_analysis(fake_image_event, fake_line_bot_api):
    agent = ImageAnalyzerAgent(http_client=AsyncMock())

    handled = await agent.handle(fake_image_event("msg-123"), "", fake_line_bot_api)

    assert handled is True
    sent = fake_line_bot_api.reply_message.call_args.kwargs["reply_message_request"].messages[0]
    assert "Would you like me to Analyze this image?" in sent.text


@pytest.mark.asyncio
async def test_yes_reply_runs_default_one_shot_analysis(
    fake_text_event,
    fake_line_bot_api,
    monkeypatch,
):
    agent = ImageAnalyzerAgent(http_client=AsyncMock())
    monkeypatch.setattr(agent, "_run_default_image_analysis", AsyncMock(return_value=True))
    chat_id = agent._get_chat_id(fake_text_event("yes"))
    user_id = fake_text_event("yes").source.user_id

    agent.session_manager.start_auto_prompt(chat_id, user_id, "data:image/jpeg;base64,abc")

    handled = await agent.handle(fake_text_event("yes"), "yes", fake_line_bot_api)

    assert handled is True
    agent._run_default_image_analysis.assert_awaited_once()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_image_analyzer_auto_prompt.py -v`

Expected: FAIL because unsolicited images are ignored unless an analysis session is already active, and `yes` has no auto-prompt branch.

- [ ] **Step 3: Write the minimal implementation**

```python
    async def should_handle(self, event: MessageEvent, text: str) -> bool:
        ...
        if message_type == "image":
            if image_analyzer_session_manager.is_waiting_for_image(chat_id, user_id):
                return True
            return True

        if message_type == "text" and text:
            text_lower = text.lower().strip()
            if image_analyzer_session_manager.is_waiting_for_auto_prompt(chat_id, user_id):
                return text_lower in {"yes", "no", "yes analyze", "no thanks"}

    async def handle(
        self, event: MessageEvent, text: str, line_bot_api: MessagingApi
    ) -> bool:
        ...
        if message_type == "image" and not image_analyzer_session_manager.is_waiting_for_image(chat_id, user_id):
            return await self._handle_unsolicited_image(event, chat_id, user_id, line_bot_api)

        if (
            message_type == "text"
            and image_analyzer_session_manager.is_waiting_for_auto_prompt(chat_id, user_id)
        ):
            return await self._handle_auto_prompt_reply(event, text, chat_id, user_id, line_bot_api)

    async def _handle_unsolicited_image(...):
        image_bytes = await self._download_image(message_id, line_bot_api)
        image_data_url = image_analyzer_service.get_image_data_url(image_bytes)
        image_analyzer_session_manager.start_auto_prompt(chat_id, user_id, image_data_url)
        quick_reply = QuickReply(
            items=[
                QuickReplyItem(type="action", action=MessageAction(label="✅ Yes", text="yes")),
                QuickReplyItem(type="action", action=MessageAction(label="❌ No", text="no")),
            ]
        )
        msg = TextMessage(
            text="Would you like me to Analyze this image?",
            quickReply=quick_reply,
            quoteToken=None,
        )
        ...

    async def _handle_auto_prompt_reply(...):
        text_lower = text.lower().strip()
        if text_lower == "no":
            image_analyzer_session_manager.clear_session(chat_id)
            ...
            return True
        if text_lower == "yes":
            return await self._run_default_image_analysis(event, chat_id, user_id, line_bot_api)
        return False

    async def _run_default_image_analysis(...):
        image_data_url, _question, _analysis_mode = image_analyzer_session_manager.get_image_and_question(
            chat_id,
            "Give a concise default description of this image, including visible text, main objects, and the most useful immediate takeaway."
        )
        analysis = await github_models_service.chat_completion_with_vision(
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Give a concise default description of this image, including visible text, main objects, and the most useful immediate takeaway.",
                        },
                        {"type": "image_url", "image_url": {"url": image_data_url}},
                    ],
                }
            ],
            model=settings.image_analyzer_model,
            temperature=0.2,
            max_tokens=700,
        )
        image_analyzer_session_manager.clear_session(chat_id)
        ...
        return True
```

- [ ] **Step 4: Run the targeted tests and the nearby regression suite**

Run: `pytest tests/test_image_analyzer_auto_prompt.py tests/test_image_analyzer_analyze_entrypoint.py tests/test_translation_agent_auto_handoff.py tests/test_session_manager.py -v`

Expected: PASS for the new auto-prompt coverage and no regressions in the existing analyze entrypoint tests

- [ ] **Step 5: Commit**

```bash
git add src/agents/image_analyzer_agent.py src/services/image_analyzer_session_manager.py tests/test_image_analyzer_auto_prompt.py tests/test_image_analyzer_analyze_entrypoint.py
git commit -m "feat: auto prompt image analysis"
```

### Task 5: Run the focused final verification

**Files:**
- Modify: none
- Test: `tests/test_session_manager.py`
- Test: `tests/test_translation_agent_auto_handoff.py`
- Test: `tests/test_image_analyzer_auto_prompt.py`
- Test: `tests/test_image_analyzer_analyze_entrypoint.py`

- [ ] **Step 1: Run the focused pytest suite**

```bash
pytest \
  tests/test_session_manager.py \
  tests/test_translation_agent_auto_handoff.py \
  tests/test_image_analyzer_auto_prompt.py \
  tests/test_image_analyzer_analyze_entrypoint.py \
  -v
```

- [ ] **Step 2: Run the broader repository tests that cover agents/services**

```bash
pytest tests -k "translation or image_analyzer or session_manager" -v
```

- [ ] **Step 3: Commit the verification-only state if anything changed during debugging**

```bash
git status --short
```

Expected: no new file edits after the last feature commit
