# AI Translation and Ms. Green Hard-Cutover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL:
> Use `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Google Translate and LibreTranslate with a shared AI
translation service, make Ms. Green the only accepted public identity, and
update help/startup/docs to match the cutover.

**Architecture:** Introduce a dedicated `AITranslationService` that wraps the
existing GitHub Models and OpenRouter provider clients with stable fallback
behavior. Apply the identity cutover through the shared identity service
first, then fix the smaller set of agents that still hard-code `zeus`
parsing or Zeus-branded responses, and finally remove legacy
translation/provider copy from startup/config/docs.

**Tech Stack:** Python, FastAPI, LINE Bot SDK v3, `httpx`, pytest, GitHub Models, OpenRouter

---

## Goals

- Centralize translation behavior in one AI-backed service.
- Rewire `TranslationAgent` and `NewsAgent` to use the shared AI translation service.
- Support `Ms. Green ...` commands and reject legacy `Zeus ...` prefixes.
- Update help output, startup metadata, and docs so they no longer
    reference Google Translate, LibreTranslate, or Zeus as the public bot
    identity.
- Remove retired translation-service runtime dependencies once their call sites are gone.

## Non-Goals

- Do not perform a full internal rename of every `zeus_*` identifier in one pass.
- Do not change agent priorities or unrelated routing behavior.
- Do not redesign the LLM/chat provider stack beyond translation-specific fallback logic.
- Do not start implementation on `main` without explicit approval or a safer worktree/branch decision.

## File Responsibilities

### New Runtime Surface

- Create: `src/services/ai_translation_service.py`
  - Shared translation orchestration using GitHub Models first and OpenRouter second.
  - Stable prompt construction, fallback, and provider metadata.

### Runtime Changes

- Modify: `src/agents/translation_agent.py`
  - Replace Google/Libre translation calls with `AITranslationService`.
  - Update wake/sleep/help copy for Ms. Green.
- Modify: `src/agents/news_agent.py`
  - Replace headline translation calls with `AITranslationService`.
- Modify: `src/services/bot_identity_service.py`
  - Support multi-word aliases like `Ms. Green`.
  - Remove `zeus` from default aliases.
- Modify: `src/agents/help_agent.py`
  - Switch help/examples/tips/header copy to Ms. Green and AI translation.
- Modify: `src/agents/document_memory_agent.py`
  - Replace hard-coded `zeus doc` parsing with identity-aware parsing.
- Modify: `src/agents/image_analyzer_agent.py`
  - Replace user-facing Zeus prompts and explicit trigger strings.
- Modify: `src/agents/profiler_agent.py`
  - Replace explicit Zeus trigger strings and visible Zeus branding.
- Modify: `src/agents/hannibal_agent.py`
  - Replace explicit `zeus hannibal` parsing with identity-aware parsing.
- Modify: `src/main.py`
  - Replace Google/Libre startup logs and health/readiness metadata with AI translation capability status.
- Modify: `src/config.py`
  - Set Ms. Green as the default identity.
  - Retire Google/Libre translation settings and add any minimal AI translation config helpers needed.
- Modify: `.env.example`
  - Remove Google/Libre translation configuration examples and update persona/help comments.

### Retire After Migration

- Delete: `src/services/google_translation.py`
- Delete: `src/services/translation_service.py`
- Delete or replace: `tests/test_translation_service.py`

### Test Surfaces

- Create: `tests/test_ai_translation_service.py`
- Create: `tests/test_translation_agent_ai.py`
- Create: `tests/test_help_agent.py`
- Create: `tests/test_document_memory_agent.py`
- Modify: `tests/test_news_language_display.py`
- Modify: `tests/test_bot_identity_service.py`
- Modify: `tests/test_bot_identity_characterization.py`
- Modify: `tests/test_private_help.py`
- Modify: `tests/test_search_agent.py`
- Modify: `tests/test_profiler_agent.py`
- Modify: `tests/test_main.py`

### Documentation Surfaces

- Modify: `README.md`
- Modify: `docs/README.md`
- Modify: `docs/KPS_ASSISTANT.md`
- Modify: `docs/NEWS_LANGUAGE_DISPLAY.md`
- Modify: `docs/reference/environment.md`
- Modify: `docs/reference/quick-reference.md`
- Modify: `docs/architecture/agents.md`
- Modify: `docs/architecture/overview.md`

---

### Task 1: Add the Shared AI Translation Service

**Files:**

- Create: `src/services/ai_translation_service.py`
- Create: `tests/test_ai_translation_service.py`

- [x] **Step 1: Write failing service tests for provider selection and fallback**

Create `tests/test_ai_translation_service.py` with focused service-level tests:

```python
import pytest
from unittest.mock import AsyncMock, Mock

from src.services.ai_translation_service import AITranslationService


@pytest.mark.asyncio
async def test_translate_uses_github_models_first():
    github = Mock()
    github.is_configured.return_value = True
    github.chat_completion = AsyncMock(return_value="สวัสดี")

    openrouter = Mock()
    openrouter.is_configured.return_value = True
    openrouter.chat_completion = AsyncMock()

    service = AITranslationService(github_models=github, openrouter=openrouter)

    result = await service.translate("Hello", source_lang="en", target_lang="th")

    assert result.text == "สวัสดี"
    assert result.provider == "github_models"
    openrouter.chat_completion.assert_not_called()


@pytest.mark.asyncio
async def test_translate_falls_back_to_openrouter_when_github_models_returns_none():
    github = Mock()
    github.is_configured.return_value = True
    github.chat_completion = AsyncMock(return_value=None)

    openrouter = Mock()
    openrouter.is_configured.return_value = True
    openrouter.chat_completion = AsyncMock(return_value="Hello")

    service = AITranslationService(github_models=github, openrouter=openrouter)

    result = await service.translate("สวัสดี", source_lang="th", target_lang="en")

    assert result.text == "Hello"
    assert result.provider == "openrouter"
```

- [x] **Step 2: Run the new service tests and confirm they fail**

Run:

```bash
cd /home/ewaldt/Documents/VS/Other/Bot/TeacherBOY
pytest tests/test_ai_translation_service.py -q
```

Expected: failure because `src/services/ai_translation_service.py` does not exist yet.

- [x] **Step 3: Implement the minimal shared AI translation service**

Create `src/services/ai_translation_service.py` with a small injectable surface:

```python
from dataclasses import dataclass
from typing import Optional

from src.services.github_models_service import github_models_service
from src.services.openrouter_service import openrouter_service


@dataclass
class AITranslationResult:
    text: str
    provider: str


class AITranslationService:
    def __init__(self, github_models=github_models_service, openrouter=openrouter_service):
        self.github_models = github_models
        self.openrouter = openrouter

    async def translate(self, text: str, source_lang: str, target_lang: str) -> Optional[AITranslationResult]:
        messages = self._build_messages(text, source_lang, target_lang)

        if self.github_models.is_configured():
            result = await self.github_models.chat_completion(messages=messages, temperature=0.2)
            if result:
                return AITranslationResult(text=result.strip(), provider="github_models")

        if self.openrouter.is_configured():
            result = await self.openrouter.chat_completion(messages=messages, temperature=0.2)
            if result:
                return AITranslationResult(text=result.strip(), provider="openrouter")

        return None

    def _build_messages(self, text: str, source_lang: str, target_lang: str) -> list[dict[str, str]]:
        return [
            {
                "role": "system",
                "content": (
                    "You are a translation engine. Translate faithfully and only return the translation. "
                    "Preserve line breaks, punctuation, emojis, and URLs. Do not explain."
                ),
            },
            {
                "role": "user",
                "content": f"Translate from {source_lang} to {target_lang}:\n\n{text}",
            },
        ]


ai_translation_service = AITranslationService()
```

- [x] **Step 4: Run the service tests again**

Run:

```bash
cd /home/ewaldt/Documents/VS/Other/Bot/TeacherBOY
pytest tests/test_ai_translation_service.py -q
```

Expected: pass.

- [x] **Step 5: Review the diff for this slice**

Run:

```bash
cd /home/ewaldt/Documents/VS/Other/Bot/TeacherBOY
git --no-pager diff -- src/services/ai_translation_service.py tests/test_ai_translation_service.py
```

Expected: only the new service and its tests appear.

---

### Task 2: Migrate TranslationAgent and NewsAgent to the Shared AI Service

**Files:**

- Modify: `src/agents/translation_agent.py`
- Modify: `src/agents/news_agent.py`
- Create: `tests/test_translation_agent_ai.py`
- Modify: `tests/test_news_language_display.py`

- [x] **Step 1: Write failing regression tests for the migrated translation paths**

Create `tests/test_translation_agent_ai.py` and update `tests/test_news_language_display.py`:

```python
@pytest.mark.asyncio
async def test_translate_message_uses_ai_translation_service():
    service = Mock()
    service.translate = AsyncMock(return_value=AITranslationResult(text="สวัสดี", provider="github_models"))

    agent = TranslationAgent(ai_translation_service=service)

    translated = await agent._translate_message("Hello", "user_123")

    assert translated == "สวัสดี"
    service.translate.assert_awaited_once_with("Hello", source_lang="en", target_lang="th")


@pytest.mark.asyncio
async def test_headlines_use_shared_ai_translation_service(news_agent):
    news_agent.ai_translation_service.translate = AsyncMock(
        return_value=AITranslationResult(text="ข่าวด่วนวันนี้", provider="github_models")
    )

    translated = await news_agent._translate_headlines_to_thai([
        {"title": "Breaking news today", "url": "https://example.com/1"},
    ])

    assert translated[0]["title"] == "ข่าวด่วนวันนี้"
```

- [x] **Step 2: Run the focused agent tests and confirm failure**

Run:

```bash
cd /home/ewaldt/Documents/VS/Other/Bot/TeacherBOY
pytest tests/test_translation_agent_ai.py tests/test_news_language_display.py -q
```

Expected: failure because the agent constructors and translation call sites still depend on Google/Libre services.

- [x] **Step 3: Replace the runtime call sites with `AITranslationService`**

Update the agents to accept an injectable AI translation dependency:

```python
from src.services.ai_translation_service import ai_translation_service, AITranslationResult


class TranslationAgent(BaseAgent):
    def __init__(self, ai_translation_service_override=ai_translation_service):
        super().__init__(name="TranslationAgent", description="Thai/English translation with continuous session mode")
        self.ai_translation_service = ai_translation_service_override

    async def _translate_message(self, text: str, chat_id: Optional[str] = None) -> str:
        source_lang = "th" if self.contains_thai(text) else "en"
        target_lang = "en" if source_lang == "th" else "th"
        result = await self.ai_translation_service.translate(text, source_lang=source_lang, target_lang=target_lang)
        if result:
            metrics_service.record_translation(result.provider, chat_id)
            return result.text
        metrics_service.record_failed_translation()
        return "Translation failed"
```

```python
class NewsAgent(BaseAgent):
    def __init__(self, news_data_service, ai_translation_service_override=ai_translation_service):
        self.news_data_service = news_data_service
        self.ai_translation_service = ai_translation_service_override

    async def _translate_headlines_to_thai(self, headlines):
        translated = []
        for headline in headlines:
            result = await self.ai_translation_service.translate(
                headline["title"], source_lang="en", target_lang="th"
            )
            translated.append({
                **headline,
                "title": result.text if result else headline["title"],
            })
        return translated
```

- [x] **Step 4: Run the same focused tests again**

Run:

```bash
cd /home/ewaldt/Documents/VS/Other/Bot/TeacherBOY
pytest tests/test_translation_agent_ai.py tests/test_news_language_display.py -q
```

Expected: pass.

- [x] **Step 5: Review the diff for unintended translation-provider leakage**

Run:

```bash
cd /home/ewaldt/Documents/VS/Other/Bot/TeacherBOY
git --no-pager diff -- src/agents/translation_agent.py src/agents/news_agent.py tests/test_translation_agent_ai.py tests/test_news_language_display.py
```

Expected: no new `google_translation_service` or `translation_service` references remain in these files.

---

### Task 3: Make the Identity Service Understand `Ms. Green` and Reject `Zeus`

**Files:**

- Modify: `src/services/bot_identity_service.py`
- Modify: `src/config.py`
- Modify: `tests/test_bot_identity_service.py`
- Modify: `tests/test_bot_identity_characterization.py`
- Modify: `tests/test_search_agent.py`

- [x] **Step 1: Write failing tests for multi-word prefix parsing and hard cutover behavior**

Add tests that reflect the actual parser limitation:

```python
def test_split_command_prefix_supports_ms_green(tmp_path):
    service = BotIdentityService(
        storage_path=tmp_path / "identity.json",
        default_name="Ms. Green",
        default_aliases=["ms. green", "ms green", "green"],
    )

    prefix, rest = service.split_command_prefix("Ms. Green search python")

    assert prefix == "ms. green"
    assert rest == "search python"


def test_split_command_prefix_rejects_legacy_zeus_after_cutover(tmp_path):
    service = BotIdentityService(
        storage_path=tmp_path / "identity.json",
        default_name="Ms. Green",
        default_aliases=["ms. green", "ms green", "green"],
    )

    prefix, rest = service.split_command_prefix("Zeus search python")

    assert prefix is None
    assert rest == "Zeus search python"
```

Extend `tests/test_search_agent.py` with a runtime alias assertion:

```python
@pytest.mark.asyncio
async def test_should_handle_ms_green_search_trigger(search_agent, message_event):
    assert await search_agent.should_handle(message_event, "Ms. Green search python") is True
```

- [x] **Step 2: Run the identity-focused tests and confirm failure**

Run:

```bash
cd /home/ewaldt/Documents/VS/Other/Bot/TeacherBOY
pytest tests/test_bot_identity_service.py tests/test_bot_identity_characterization.py tests/test_search_agent.py -q
```

Expected: failure because the current parser only inspects the first token and the defaults still include `zeus`.

- [x] **Step 3: Implement multi-word alias matching and update defaults to Ms. Green**

Update `src/services/bot_identity_service.py` and `src/config.py`:

```python
DEFAULT_BOT_IDENTITY_NAME = "Ms. Green"
DEFAULT_BOT_IDENTITY_ALIASES = [
    "ms. green",
    "ms green",
    "green",
    "ms",
]


def split_command_prefix(self, text: str) -> tuple[str | None, str]:
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    if cleaned.startswith("/"):
        cleaned = cleaned[1:].lstrip()
    lowered = cleaned.lower()

    for alias in sorted(self._profile.aliases, key=len, reverse=True):
        if lowered == alias:
            return alias, ""
        if lowered.startswith(f"{alias} "):
            return alias, cleaned[len(alias):].lstrip()

    return None, cleaned
```

```python
bot_identity_default_name: str = Field(default="Ms. Green")
bot_identity_default_aliases: str = Field(default="ms. green,ms green,green,ms")
```

- [x] **Step 4: Re-run the same identity-focused tests**

Run:

```bash
cd /home/ewaldt/Documents/VS/Other/Bot/TeacherBOY
pytest tests/test_bot_identity_service.py tests/test_bot_identity_characterization.py tests/test_search_agent.py -q
```

Expected: pass.

- [x] **Step 5: Review the diff for accidental alias expansion**

Run:

```bash
cd /home/ewaldt/Documents/VS/Other/Bot/TeacherBOY
git --no-pager diff -- src/services/bot_identity_service.py src/config.py tests/test_bot_identity_service.py tests/test_bot_identity_characterization.py tests/test_search_agent.py
```

Expected: only Ms. Green aliases are recognized by default, and no `zeus` alias remains in runtime defaults.

---

### Task 4: Apply the Hard Cutover to Help and the Remaining Direct-Command Agents

**Files:**

- Modify: `src/agents/help_agent.py`
- Modify: `src/agents/translation_agent.py`
- Modify: `src/agents/document_memory_agent.py`
- Modify: `src/agents/image_analyzer_agent.py`
- Modify: `src/agents/profiler_agent.py`
- Modify: `src/agents/hannibal_agent.py`
- Create: `tests/test_help_agent.py`
- Create: `tests/test_document_memory_agent.py`
- Modify: `tests/test_private_help.py`
- Modify: `tests/test_profiler_agent.py`

- [x] **Step 1: Write failing tests for Ms. Green help text and direct-command triggers**

Add or update tests around the visible cutover behavior:

```python
@pytest.mark.asyncio
async def test_help_output_uses_ms_green_and_ai_translation(help_agent, private_event, line_bot_api):
    await help_agent.handle(private_event, "help", line_bot_api)
    text = line_bot_api.reply_message.call_args[0][0].messages[0].alt_text
    assert "Ms. Green" in text
    assert "Google Translate" not in text
    assert "LibreTranslate" not in text
    assert "Zeus" not in text


@pytest.mark.asyncio
async def test_document_memory_agent_accepts_ms_green_prefix():
    agent = DocumentMemoryAgent(document_service=Mock())
    assert await agent.should_handle(event, "Ms. Green docs") is True
    assert await agent.should_handle(event, "Zeus docs") is False
```

Extend `tests/test_profiler_agent.py` so face-analysis triggers use `Ms. Green profile` instead of `zeus profile`.

- [x] **Step 2: Run the direct-command cutover tests and confirm failure**

Run:

```bash
cd /home/ewaldt/Documents/VS/Other/Bot/TeacherBOY
pytest tests/test_help_agent.py tests/test_private_help.py tests/test_document_memory_agent.py tests/test_profiler_agent.py -q
```

Expected: failure because the agents and help content still contain hard-coded Zeus strings.

- [x] **Step 3: Update direct parsers and visible copy to Ms. Green**

Use the shared identity service anywhere a parser still assumes literal `zeus`:

```python
identity_service = get_bot_identity_service()
prefix, rest = identity_service.split_command_prefix(text)
if prefix and rest.startswith("doc"):
    ...
```

Update translation-agent wake/sleep/help copy:

```python
def is_wake_command(self, text: str) -> bool:
    prefix, _ = get_bot_identity_service().split_command_prefix(text)
    return prefix is not None

def is_sleep_command(self, text: str) -> bool:
    text_lower = re.sub(r"\s+", " ", text.lower().strip())
    return text_lower in {"good night ms. green", "good night ms green", "sleep ms. green", "sleep ms green", "ms. green sleep", "ms green sleep", "amen"}
```

Update help content so examples and tips say `Ms. Green ...`, and describe translation as AI-powered.

- [x] **Step 4: Run the same direct-command cutover tests again**

Run:

```bash
cd /home/ewaldt/Documents/VS/Other/Bot/TeacherBOY
pytest tests/test_help_agent.py tests/test_private_help.py tests/test_document_memory_agent.py tests/test_profiler_agent.py -q
```

Expected: pass.

- [x] **Step 5: Review the diff for remaining user-facing Zeus strings in the touched runtime files**

Run:

```bash
cd /home/ewaldt/Documents/VS/Other/Bot/TeacherBOY
rg -n "Zeus|Dear Zeus|Google Translate|LibreTranslate" src/agents/help_agent.py src/agents/translation_agent.py src/agents/document_memory_agent.py src/agents/image_analyzer_agent.py src/agents/profiler_agent.py src/agents/hannibal_agent.py
```

Expected: only non-user-facing comments may remain; no live command examples or user-visible response text should match.

---

### Task 5: Remove Legacy Provider Surfaces, Update Startup Metadata, and Refresh Docs

**Files:**

- Modify: `src/main.py`
- Modify: `.env.example`
- Modify: `README.md`
- Modify: `docs/README.md`
- Modify: `docs/KPS_ASSISTANT.md`
- Modify: `docs/NEWS_LANGUAGE_DISPLAY.md`
- Modify: `docs/reference/environment.md`
- Modify: `docs/reference/quick-reference.md`
- Modify: `docs/architecture/agents.md`
- Modify: `docs/architecture/overview.md`
- Modify: `tests/test_main.py`
- Delete: `src/services/google_translation.py`
- Delete: `src/services/translation_service.py`
- Delete or replace: `tests/test_translation_service.py`

- [x] **Step 1: Add failing tests for the new startup metadata contract**

Update `tests/test_main.py` so root/readiness assertions stop expecting Google-specific fields:

```python
def test_root_reports_ai_translation_backend(client):
    response = client.get("/")
    payload = response.json()

    assert payload["features"]["translation"] == "AI translation"
    assert payload["features"]["translation_backend"] == "ai"
    assert "google_translate" not in payload["features"]


def test_readiness_does_not_expose_google_translate_flag(client):
    response = client.get("/readiness")
    payload = response.json()

    assert "google_translate_enabled" not in payload
    assert payload["translation_backend"] == "ai"
```

- [x] **Step 2: Run the startup tests and confirm failure**

Run:

```bash
cd /home/ewaldt/Documents/VS/Other/Bot/TeacherBOY
pytest tests/test_main.py -q
```

Expected: failure because `src/main.py` still logs/configures Google/Libre translation and exposes `google_translate_enabled`.

- [x] **Step 3: Replace startup/config/docs surfaces and retire the old services**

Update startup metadata and logs:

```python
logger.info("✅ AI translation configured (GitHub Models -> OpenRouter fallback)")

return {
    "status": "operational",
    "service": "Ms. Green Assistant",
    "version": "3.0.0",
    "features": {
        "translation": "AI translation",
        "translation_backend": "ai",
    },
}
```

```python
return {
    "ready": ready,
    "checks": {...},
    "translation_backend": "ai",
}
```

Then delete `src/services/google_translation.py` and
`src/services/translation_service.py` after the repo no longer imports them,
and replace translation-provider docs/examples with Ms. Green + AI wording.

- [x] **Step 4: Run the focused verification suites for runtime, help, identity, and translation**

Run:

```bash
cd /home/ewaldt/Documents/VS/Other/Bot/TeacherBOY
pytest tests/test_ai_translation_service.py tests/test_translation_agent_ai.py tests/test_news_language_display.py tests/test_help_agent.py tests/test_private_help.py tests/test_bot_identity_service.py tests/test_bot_identity_characterization.py tests/test_search_agent.py tests/test_main.py -q
```

Expected: pass.

- [x] **Step 5: Run a repo-wide grep to confirm the public cutover is complete in canonical docs and env examples**

Run:

```bash
cd /home/ewaldt/Documents/VS/Other/Bot/TeacherBOY
rg -n "Google Translate|LibreTranslate|Dear Zeus|Zeus search|Zeus calendar|zeus profile" README.md docs .env.example
```

Expected: no matches in canonical user/operator docs or env comments,
except inside archived historical plan/spec files under
`docs/superpowers/`.

---

## Final Verification

- [x] **Step 1: Run the full repository test suite**

Run:

```bash
cd /home/ewaldt/Documents/VS/Other/Bot/TeacherBOY
pytest -q
```

Expected: pass, or only pre-existing unrelated failures are documented explicitly before continuing.

- [x] **Step 2: Run coverage and capture the result honestly**

Run:

```bash
cd /home/ewaldt/Documents/VS/Other/Bot/TeacherBOY
pytest --cov=src --cov-report=term-missing -q
```

Expected: coverage remains at or above the repo target, or any drop is reported explicitly.

Observed: the suite passed, but
`pytest --cov=src --cov-report=term-missing -q` reported 46% total
coverage, so the documented repo target is not currently met.

- [x] **Step 3: Review the final diff before handoff**

Run:

```bash
cd /home/ewaldt/Documents/VS/Other/Bot/TeacherBOY
git --no-pager diff --stat
git --no-pager diff
```

Expected: only translation, identity, startup, help, and documentation surfaces changed for this cutover.

- [x] **Step 4: Prepare handoff notes**

Include this checklist in the final summary:

```text
- Shared AI translation service added and wired into translation + news flows
- Ms. Green is the only accepted public command prefix
- Help output and startup metadata updated for AI translation
- Google Translate and LibreTranslate runtime services removed
- Canonical docs and .env example updated for the hard cutover
- Focused tests, full tests, and coverage results recorded
```
