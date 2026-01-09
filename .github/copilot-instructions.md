# TeacherBOY (Zeus) — Copilot Instructions

## 📑 File Index (Context Optimization)

**⚠️ READ THIS FIRST to avoid unnecessary token usage!**

### 🔍 Quick File Lookup by Feature

<details>
<summary><b>Core System Files (Start Here)</b></summary>

- **Entry Point**: [src/main.py](../src/main.py) — FastAPI app, webhook, lifespan
- **Routing**: [src/agents/agent_router.py](../src/agents/agent_router.py) — Priority-based message routing
- **Config**: [src/config.py](../src/config.py) — All environment settings with validation
- **Base Agent**: [src/agents/base_agent.py](../src/agents/base_agent.py) — Abstract class for all agents

</details>

<details>
<summary><b>Agents (by Priority)</b></summary>

1. **Priority 5**: [src/agents/help_agent.py](../src/agents/help_agent.py) — Contextual help
2. **Priority 5**: [src/agents/admin_agent.py](../src/agents/admin_agent.py) — Admin commands
3. **Priority 6**: [src/agents/calendar_agent.py](../src/agents/calendar_agent.py) — Events & reminders
4. **Priority 7**: [src/agents/profiler_agent.py](../src/agents/profiler_agent.py) — Image psychological profiling
5. **Priority 7**: [src/agents/image_analyzer_agent.py](../src/agents/image_analyzer_agent.py) — Image Q&A
6. **Priority 8**: [src/agents/search_agent.py](../src/agents/search_agent.py) — Web search
7. **Priority 9**: [src/agents/llm_agent.py](../src/agents/llm_agent.py) — Zeus AI chat
8. **Priority 10**: [src/agents/translation_agent.py](../src/agents/translation_agent.py) — Thai↔English (default)
9. **Priority 12**: [src/agents/special_news_agent.py](../src/agents/special_news_agent.py) — Interactive news
10. **Priority 15**: [src/agents/news_agent.py](../src/agents/news_agent.py) — Weather/headlines

</details>

<details>
<summary><b>Services (Business Logic)</b></summary>

**Translation**:
- [src/services/google_translation.py](../src/services/google_translation.py) — Google Translate (primary)
- [src/services/translation_service.py](../src/services/translation_service.py) — LibreTranslate (fallback)
- [src/utils/text_preprocessing.py](../src/utils/text_preprocessing.py) — Parenthesis preservation, incomplete detection

**AI/LLM**:
- [src/services/github_models_service.py](../src/services/github_models_service.py) — GitHub Models API (primary)
- [src/services/openrouter_service.py](../src/services/openrouter_service.py) — OpenRouter API (fallback)
- [src/services/conversation_memory_service.py](../src/services/conversation_memory_service.py) — Multi-turn memory
- [src/services/conversation_summary_service.py](../src/services/conversation_summary_service.py) — Token reduction

**Vision/Profiling**:
- [src/services/profiler_service.py](../src/services/profiler_service.py) — Profiling prompts & logic
- [src/prompts/builders/vision_builder.py](../src/prompts/builders/vision_builder.py) — Modular prompt system
- [src/prompts/frameworks/ekman_facs.py](../src/prompts/frameworks/ekman_facs.py) — Ekman FACS framework
- [src/prompts/frameworks/fbi_bau.py](../src/prompts/frameworks/fbi_bau.py) — FBI BAU framework

**Calendar**:
- [src/services/calendar_service.py](../src/services/calendar_service.py) — Event storage/retrieval
- [src/services/calendar_session_manager.py](../src/services/calendar_session_manager.py) — Multi-step flows
- [src/services/reminder_service.py](../src/services/reminder_service.py) — Daily reminder scheduler
- [src/services/date_extraction_service.py](../src/services/date_extraction_service.py) — AI date parsing
- [src/services/message_buffer_service.py](../src/services/message_buffer_service.py) — Message history for scrape

**News/Data**:
- [src/services/news_data_service.py](../src/services/news_data_service.py) — Weather, headlines, crypto
- [src/services/special_news_service.py](../src/services/special_news_service.py) — Thailand news/tourism
- [src/services/news_session_manager.py](../src/services/news_session_manager.py) — News flow state

**Infrastructure**:
- [src/services/rate_limiter.py](../src/services/rate_limiter.py) — Rate limiting
- [src/services/privilege_service.py](../src/services/privilege_service.py) — Admin/moderator checks
- [src/services/metrics_service.py](../src/services/metrics_service.py) — Performance tracking
- [src/services/prompt_metrics.py](../src/services/prompt_metrics.py) — Token usage tracking
- [src/services/scheduler_service.py](../src/services/scheduler_service.py) — Background tasks
- [src/services/history_log_service.py](../src/services/history_log_service.py) — Event logging

</details>

<details>
<summary><b>Session Managers (State Machines)</b></summary>

- [src/services/session_manager.py](../src/services/session_manager.py) — Translation session state
- [src/services/news_session_manager.py](../src/services/news_session_manager.py) — News flow (14+ states)
- [src/services/calendar_session_manager.py](../src/services/calendar_session_manager.py) — Calendar flow
- [src/services/profiler_session_manager.py](../src/services/profiler_session_manager.py) — Profiler flow
- [src/services/image_analyzer_session_manager.py](../src/services/image_analyzer_session_manager.py) — Image Q&A flow

</details>

<details>
<summary><b>❌ DO NOT READ (Unless Specifically Needed)</b></summary>

**Tests** — Only read if debugging test failures:
- `tests/test_*.py` — Test files (50+ files)

**Documentation** — Only for reference:
- `docs/*.md` — User guides and architecture docs
- `*.md` files in root — Changelogs, reviews, guides

**Generated/Config** — Rarely need to read:
- `requirements.txt`, `Dockerfile`, `docker-compose.yml`
- `pytest.ini`, `cspell.json`
- `data/`, `__pycache__/`, `.env` files

**Deprecated** — Do NOT use:
- [src/handlers/message_handler.py](../src/handlers/message_handler.py) — LEGACY, use agent_router instead

</details>

### 🎯 Common Tasks → Files Needed

| Task | Primary Files | Supporting Files |
|------|--------------|------------------|
| Add new agent | `base_agent.py`, `main.py`, `agent_router.py` | `config.py` for settings |
| Fix translation | `translation_agent.py`, `google_translation.py` | `text_preprocessing.py` |
| Debug news flow | `news_agent.py`, `news_session_manager.py` | `news_data_service.py` |
| Calendar issue | `calendar_agent.py`, `calendar_session_manager.py` | `calendar_service.py`, `reminder_service.py` |
| Add config setting | `config.py`, `.env.example` | Relevant agent/service file |
| Profiler optimization | `profiler_agent.py`, `vision_builder.py` | Framework files in `prompts/frameworks/` |
| Rate limit change | `rate_limiter.py` | Relevant agent file |
| Admin command | `admin_agent.py` | `privilege_service.py` |

---

## Architecture & flow

- Entry point is [src/main.py](../src/main.py): FastAPI app + `lifespan` startup, `/webhook`, shared `httpx.AsyncClient`.
- Webhook flow: validate LINE signature → skip self-messages (`bot_user_id`) → route text via [src/agents/agent_router.py](../src/agents/agent_router.py).
- Agent routing is **first-match wins** in **ascending** `get_priority()`; only one agent should handle a message.

## Agent conventions

- Implement agents by subclassing [src/agents/base_agent.py](../src/agents/base_agent.py) with async `should_handle()` + async `handle()`.
- Choose priorities carefully: `<10` preempts translation; default translation is [src/agents/translation_agent.py](../src/agents/translation_agent.py) at `10`.
- Runtime (in-memory) admin is tracked by [src/services/privilege_service.py](../src/services/privilege_service.py) (used by `/admin claim …`).

## LINE + async I/O rules

- LINE SDK v3 calls are sync; in async code wrap them with `await asyncio.to_thread(...)` (see patterns in [src/main.py](../src/main.py)).
- Do not create new `httpx.AsyncClient` instances; reuse the singleton created in `lifespan` and injected into services.

## Feature-specific gotchas

- Do not modify [src/handlers/message_handler.py](../src/handlers/message_handler.py) for production behavior; it’s legacy (agent router is the real path).
- News is stateful and friend-gated: groups/rooms require friend check via LINE `get_profile`; non-friends (and most private chats) get “trigger translation” only (see [src/agents/news_agent.py](../src/agents/news_agent.py)).
- Translation uses preprocessing: preserve parentheses + mark incomplete sentences (see [src/utils/text_preprocessing.py](../src/utils/text_preprocessing.py)).

## Testing & debugging

- Run tests with `pytest` (asyncio mode is enabled in [pytest.ini](../pytest.ini)). Prefer targeting a single file first (e.g. `pytest tests/test_news_agent.py`).
- When changing env-driven behavior in tests: agents cache admin IDs in `__init__`, and tests often patch **module-local** `settings` before instantiation.

## Observability

- Tracing is optional; enable via `ENABLE_TRACING=true` and see [docs/TRACING.md](../docs/TRACING.md). Tracing setup lives in [src/utils/tracing.py](../src/utils/tracing.py).

## Key env vars (feature gates)

- Required: `LINE_CHANNEL_SECRET`, `LINE_CHANNEL_ACCESS_TOKEN`.
- Translation: `GOOGLE_TRANSLATE_API_KEY` (primary; otherwise LibreTranslate fallback).
- Search: `BRAVE_SEARCH_API_KEY`.
- LLM: `GITHUB_MODELS_PAT` and/or `OPENROUTER_API_KEY`, plus `LLM_PROVIDER_PRIORITY`.

# TeacherBOY — AI Coding Agent Instructions

## 🎯 Quick Context

**What:** Production LINE bot with async multi-agent architecture. Thai ↔ English translation is the primary feature, with optional admin commands, news/weather data, and LLM Q&A.

**Key files:**

- Entry point: [src/main.py](../src/main.py) — FastAPI app with `lifespan` context, `/webhook` endpoint, HTTP client pool
- Agent dispatch: [src/agents/agent_router.py](../src/agents/agent_router.py) — priority-based routing
- Base contract: [src/agents/base_agent.py](../src/agents/base_agent.py) — abstract `should_handle()` + async `handle()`
- Settings: [src/config.py](../src/config.py) — Pydantic settings with environment validation

## 🔄 Webhook Flow

```
LINE POST /webhook → Validate signature → Skip bot's own messages (bot_user_id check)
  ↓
AgentRouter.route_message() → try agents in priority order (ascending)
  ↓
First agent with should_handle()=True wins → calls handle()
```

**Critical:** Agents run in **ascending** `get_priority()` order; first match wins. **Async-only** — all agent methods must be `async def`.

## 🤖 Agent Hierarchy

| Agent                | Priority | Trigger               | Notes                                                              |
| -------------------- | -------- | --------------------- | ------------------------------------------------------------------ |
| **HelpAgent**        | 5        | `help`, `/help`       | Contextual help; shows different commands per chat type/privileges |
| **AdminAgent**       | 5        | `/admin ...`          | Registered if `ADMIN_USER_IDS` or `ADMIN_SETUP_KEY` is set         |
| **CalendarAgent**    | 6        | `zeus calendar`, etc. | Events/reminders with scrape & inline add (see Calendar section)   |
| **ProfilerAgent**    | 7        | Image message         | Psychological profiling using FBI/Ekman/Navarro frameworks         |
| **SearchAgent**      | 8        | `Zeus search <query>` | Conditional: requires `BRAVE_SEARCH_API_KEY`                       |
| **LLMAgent**         | 9        | `Zeus <prompt>`       | GitHub Models → OpenRouter fallback; conversation memory           |
| **TranslationAgent** | 10       | Default/fallback      | Thai ↔ English; Google Translate → LibreTranslate fallback         |
| **SpecialNewsAgent** | 12       | `/special news`       | DM-only interactive news carousel                                  |
| **NewsAgent**        | 15       | `news` or `ข่าว`      | Friend-gated in groups; admins/moderators get full menu in DMs     |

## 📰 News Access Model

| Context      | User Type                      | Response                                     |
| ------------ | ------------------------------ | -------------------------------------------- |
| Group/Room   | Friend (verified via LINE API) | Full menu: weather, PM2.5, stocks, headlines |
| Group/Room   | Non-friend                     | Trigger translation only: `news → ข่าว`      |
| Private Chat | Admin/Moderator                | Full menu                                    |
| Private Chat | Regular user                   | Trigger translation only                     |

## ⏱️ Rate Limiting

- **TranslationAgent:** 10 requests/60s per chat (admins: unlimited)
- **NewsAgent:** 1 request/hour for friends in groups (admins: unlimited)
- **ProfilerAgent:** 3 requests/hour per chat (admins: unlimited, vision API is expensive)
- **Admin check:** `_is_admin(user_id)` + `privilege_service.is_claimed_admin(user_id)`

## 🔬 Psychological Profiler

The ProfilerAgent analyzes photos using GPT-4o vision with established behavioral science frameworks:

**Frameworks Used:**

- **FBI BAU Methodology** — Behavioral Analysis Unit patterns (victimology, cognitive load, social dynamics)
- **Paul Ekman's FACS** — Facial Action Coding System, 7 universal emotions (Happiness, Sadness, Fear, Anger, Surprise, Disgust, Contempt)
- **Joe Navarro's Body Language** — FBI-trained nonverbal communication (limbic responses, honest body parts, comfort/discomfort indicators)
- **Color Psychology** — Environmental and clothing color analysis

**Configuration:**

```env
PROFILER_ENABLED=true                    # Enable/disable feature
PROFILER_MODEL=openai/gpt-4o            # Vision-capable model
PROFILER_ANALYSIS_TYPE=full             # full|quick|body|facial
PROFILER_RATE_LIMIT_PER_HOUR=3          # API cost protection
```

**Key Files:**

- [src/agents/profiler_agent.py](../src/agents/profiler_agent.py) — Agent handling image messages
- [src/services/profiler_service.py](../src/services/profiler_service.py) — Profiling logic and prompts
- [src/services/github_models_service.py](../src/services/github_models_service.py) — `chat_completion_with_vision()` method

**Disclaimer:** Educational/entertainment purposes only.

## � Calendar Agent

The CalendarAgent manages events and reminders with multi-step flows, AI-powered date extraction, and inline add capability.

**Triggers:**

| Command                     | Description                              |
| --------------------------- | ---------------------------------------- |
| `zeus calendar`             | Show calendar menu                       |
| `zeus events`               | List upcoming events                     |
| `zeus add event`            | Start interactive add flow               |
| `zeus scrape` / `zeus scan` | AI-scan last 10 messages for dates       |
| `zeus add [date] [title]`   | Inline add with date (see formats below) |

**Supported Date Formats (Inline Add):**

- `tomorrow` — next calendar day
- `today` — current day
- `in X days` — relative days (e.g., `in 3 days`, `in 7 days`)
- `Jan 15` / `January 15` — named month + day (current/next year)
- `15/01/2025` — DD/MM/YYYY format
- `2025-06-15` — ISO format (YYYY-MM-DD)

**Not supported:** "next week" (too ambiguous)

**Zeus Scrape Flow:**

1. User sends `zeus scrape`
2. Bot retrieves last 10 messages from local buffer (LINE API doesn't provide history)
3. GPT-4o-mini extracts dates/events with confidence scores
4. User reviews each event: [Yes ✓] [No ✗] [Skip →]
5. If accepted, user selects reminder days: [7 days] [3 days] [1 day] [All]
6. Event saved to calendar

**Zeus Add Inline Flow:**

1. User sends `zeus add tomorrow Team standup`
2. Bot parses date and title, shows confirmation
3. User selects reminder days via Quick Reply
4. Event saved to calendar

**Key Files:**

- [src/agents/calendar_agent.py](../src/agents/calendar_agent.py) — Agent with triggers and handlers
- [src/services/calendar_service.py](../src/services/calendar_service.py) — Event storage and retrieval
- [src/services/calendar_session_manager.py](../src/services/calendar_session_manager.py) — Multi-step flow state machine
- [src/services/message_buffer_service.py](../src/services/message_buffer_service.py) — Local message storage for scrape
- [src/services/date_extraction_service.py](../src/services/date_extraction_service.py) — AI-powered date extraction

**Configuration:**

```env
CALENDAR_ENABLED=true                    # Enable/disable feature
CALENDAR_DATA_PATH=./data/calendar       # Local storage path
CALENDAR_HF_REPO_ID=user/repo            # Optional HF Hub sync
CALENDAR_REMINDER_HOUR=8                 # Daily reminder hour (Bangkok time)
```

**Architecture Notes:**

- LINE Messaging API does NOT provide message history retrieval (webhook-only)
- MessageBufferService stores last 20 messages per chat with 2-hour TTL
- DateExtractionService uses GPT-4o-mini with regex fallback
- CalendarSessionManager has 14+ states for complex flows

## �🛠️ Developer Workflows

```bash
# Local development
python -m uvicorn src.main:app --reload --port 8000

# Docker
docker-compose up --build

# Testing (pytest with asyncio auto mode - see pytest.ini)
pytest                                    # All tests
pytest --cov=src --cov-report=html       # With coverage
pytest tests/test_news_agent.py          # Single file
```

## ➕ Adding a New Agent

1. Create `src/agents/<your_agent>.py` subclassing `BaseAgent`
2. Implement:
   - `async def should_handle(event, text) -> bool`
   - `async def handle(event, text, line_bot_api) -> bool`
   - `def get_priority() -> int` (lower = runs first; use <10 only if must preempt translation)
3. Register in `src/main.py` lifespan:
   ```python
   agent_router.register_agent(YourAgent())
   ```

## 📝 Code Patterns

**Logging:** `logger = logging.getLogger(__name__)` with emoji prefixes (✅/❌/🔍/⚠️)

**Tracing:** `from src.utils.tracing import get_tracer` → `tracer.start_as_current_span()`

**LINE SDK v3 async:** Use `await asyncio.to_thread(...)` for sync LINE API calls:

```python
await asyncio.to_thread(line_bot_api.reply_message, ReplyMessageRequest(...))
```

**Chat ID extraction:** Normalize to `user_<id>`, `group_<id>`, `room_<id>`:

```python
def _get_chat_id(self, event: MessageEvent) -> str:
    if group_id := getattr(event.source, "group_id", None): return f"group_{group_id}"
    if room_id := getattr(event.source, "room_id", None): return f"room_{room_id}"
    return f"user_{getattr(event.source, 'user_id', 'unknown')}"
```

**Admin checks:** Combine env-based + runtime-claimed:

```python
def _is_admin(self, user_id: Optional[str]) -> bool:
    if privilege_service.is_claimed_admin(user_id): return True
    return user_id in self._admin_user_ids if user_id else False
```

**HTTP client:** Reuse the singleton `httpx.AsyncClient` from `src/main.py` lifespan—never create new ones.

## ⚠️ Known Gotchas

- **Do not edit** [src/handlers/message_handler.py](../src/handlers/message_handler.py) — legacy Flex handler; production uses agent routing
- **Self-message loop:** Handled in webhook via `bot_user_id` check
- **Async-only:** No `time.sleep()` or blocking I/O—use `await asyncio.sleep()` and async libraries
- **LINE SDK v3:** Use `linebot.v3.webhooks` and `linebot.v3.messaging`; avoid v2 imports
- **Tests patch `settings`:** Agents cache `settings.get_admin_user_ids()` in `__init__`; tests must patch module-local `settings` before instantiation
- **HF Spaces Docker:** Avoid nested `src/` directories; Dockerfile runs from top-level `src/`

## 🌐 Translation Provider Stack

1. **Primary:** Google Translate ([src/services/google_translation.py](../src/services/google_translation.py)) — auto-retry via `@with_retry()`
2. **Fallback:** LibreTranslate ([src/services/translation_service.py](../src/services/translation_service.py))
3. **Text preprocessing:** Parentheses preserved, incomplete sentence detection in [src/utils/text_preprocessing.py](../src/utils/text_preprocessing.py)

## 📊 Data Services

| Service                                                                      | API              | Cache TTL |
| ---------------------------------------------------------------------------- | ---------------- | --------- |
| Weather/PM2.5 ([news_data_service.py](../src/services/news_data_service.py)) | Open-Meteo       | 30 min    |
| Holidays                                                                     | `holidays` lib   | 7 days    |
| Crypto (BTC/ETH/USDT)                                                        | CoinGecko        | 5 min     |
| Exchange rates                                                               | ExchangeRate-API | 1 hour    |
| News headlines                                                               | Bangkok Post RSS | 1 hour    |

## 🔧 Environment Variables (Key)

```env
LINE_CHANNEL_SECRET, LINE_CHANNEL_ACCESS_TOKEN  # Required
GOOGLE_TRANSLATE_API_KEY                        # Primary translation
ADMIN_USER_IDS                                  # Comma-separated admin LINE IDs
MODERATOR_USER_IDS                              # Comma-separated moderator IDs
GITHUB_MODELS_PAT                               # For Zeus AI (priority)
OPENROUTER_API_KEY                              # Zeus AI fallback
BRAVE_SEARCH_API_KEY                            # Zeus search feature
LLM_PROVIDER_PRIORITY=github,openrouter         # LLM provider order
```

See [src/config.py](../src/config.py) for full list with validation ranges.
