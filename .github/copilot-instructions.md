# TeacherBOY — AI Coding Agent Instructions

## 📋 Index

- [🎯 Quick Context](#-quick-context)
- [🔄 Webhook Flow](#-webhook-flow-read-first)
- [🤖 Agent Hierarchy](#-agent-hierarchy-priority-order)
- [📰 News Access Model](#-news-access-model)
- [📰 Extended News Menu](#-extended-news-menu-8-items-for-friends)
- [⏱️ Rate Limiting](#️-rate-limiting-rules)
- [📋 Session & Rate-Limiting Rules](#-session--rate-limiting-rules-translationagent-only)
- [🌐 Translation Provider Stack](#-translation-provider-stack)
- [🛠️ Developer Workflows](#️-developer-workflows)
- [➕ Adding a New Agent](#-adding-a-new-agent-pattern)
- [📝 Code Patterns to Follow](#-code-patterns-to-follow)
- [⚠️ Known Gotchas & Legacy](#️-known-gotchas--legacy)

## 🎯 Quick Context

**What:** Production LINE bot with async multi-agent architecture. Thai ↔ English translation is the primary feature, with optional admin commands and news/weather data.

**Key files:**

- Entry point: [src/main.py](../src/main.py) — FastAPI app with `lifespan` context, `/webhook` endpoint, HTTP client pool
- Agent dispatch: [src/agents/agent_router.py](../src/agents/agent_router.py) — priority-based routing
- Base contract: [src/agents/base_agent.py](../src/agents/base_agent.py) — abstract `should_handle()` + async `handle()`

## 🔄 Webhook Flow (Read First)

```
LINE sends POST → FastAPI /webhook
  ↓
Validate signature (InvalidSignatureError if fails)
  ↓
Skip self-messages via bot_user_id check (prevents loops)
  ↓
AgentRouter.route_message() → try agents in priority order
  ↓
First agent with should_handle()=true → calls handle()
```

**Critical:** Agents run **in ascending priority order** (`get_priority()`); first match wins. The event loop is **async-only** — all agent methods are `async def`.

## 🤖 Agent Hierarchy (Priority Order)

| Agent                | Priority | Status      | Trigger                                   | Notes                                                                                                                                                                                                                                                 |
| -------------------- | -------- | ----------- | ----------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **AdminAgent**       | 5        | Conditional | `/admin` or `!admin` prefix               | Only registered if `ADMIN_USER_IDS` env is set                                                                                                                                                                                                        |
| **TranslationAgent** | 10       | Always on   | Non-admin messages (fallback)             | Detects language, calls Google or LibreTranslate, applies session/rate-limit rules                                                                                                                                                                    |
| **NewsAgent**        | 15       | Conditional | `news` or `ข่าว` (group-only for friends) | **Friend-gated**: Groups—friends see full 8-item menu (weather, PM2.5, legal, color, holidays, Bitcoin, rates); non-friends get trigger translation only. Private chats always translate trigger. See [News Access Model](#-news-access-model) below. |

## � News Access Model

**NewsAgent enforces friend-based access control:**

| Context          | Trigger          | User Type                      | Response                                                   |
| ---------------- | ---------------- | ------------------------------ | ---------------------------------------------------------- |
| **Group/Room**   | `news` or `ข่าว` | Friend (verified via LINE API) | Full menu: weather, PM2.5, stocks, headlines (1–5 options) |
| **Group/Room**   | `news` or `ข่าว` | Non-friend                     | Trigger translation only: `news → ข่าว` or vice versa      |
| **Private Chat** | `news` or `ข่าว` | Any user                       | Trigger translation only (no menu/data shown)              |

**Implementation**:

- `_is_group_chat(event)` → checks for `group_id` or `room_id`
- `await _is_friend(event, line_bot_api)` → calls LINE API `get_profile(user_id)`; returns `False` on `ApiException`
- `_send_trigger_translation(...)` → responds with translated keyword only (robotic, no chatter)

## ⏱️ Rate Limiting

**Rate limiting enforces fair usage and prevents API quota exhaustion:**

### TranslationAgent Rate Limits

- **Default Users:** 10 requests per 60 seconds per chat
- **Admin Users:** Unlimited (bypass all rate limits)
- **Implementation:** `rate_limiter.is_allowed(chat_id)` check in `handle()` method
- **Admin Check:** `_is_admin(user_id)` returns True if user in `settings.get_admin_user_ids()`

### NewsAgent Rate Limits

- **Friend Users (groups):** 1 news request per hour (3600 seconds)
- **Non-Friends (groups):** Translation only (no menu access)
- **Private Chats:** Translation only (no menu access)
- **Admin Users:** Unlimited (bypass all rate limits)
- **Implementation:** `news_rate_limiter_friend.is_allowed(chat_id)` check before menu display
- **Rate Limiter:** `RateLimiter(max_requests=1, time_window_seconds=3600)`

### Rate Limit Response

When rate limited, users receive:

```text
⏳ Only 1 news request per hour
Total requests left: 0

Try again in ~45 minutes

คุณขอข่าวเร็วเกินไปค่ะ! 📰
เหลืออีก: 0 ครั้ง
กรุณารอ ~45 นาที 😊
```

**Admin Bypass Logging:**

- `"🔓 Admin {user_id} bypassed rate limit"` for TranslationAgent
- `"🔓 Admin {user_id} bypassed news rate limit"` for NewsAgent

## 📰 Extended News Menu (8 Items for Friends)

**Menu Structure:**

1. **Weather & Air Quality** 🌡️💨 → Bangkok temperature + PM2.5 (Open-Meteo)
2. **Rain Forecast** 🌧️ → 5-hour rain prediction (Open-Meteo)
3. **Legal Info** 🍃🚭🍺 → Cannabis, e-cigs, alcohol status (static Thai law)
4. **Lucky Color + Sunsets** 🎨🌅 → Daily lucky color (365-color cycle) + sunrise/sunset times
5. **Headlines** 📰 → Top 5 news stories (NewsAPI or placeholders)
6. **Thai Holidays + Markets** 📅🏛️ → Major holidays + SET market status (holidays library + static fallback)
7. **Bitcoin Price** ₿ → BTC/USD + 24h change (CoinGecko, free, no key)
8. **Exchange Rates** 💱 → THB→USD, THB→ZAR, THB→CNY (ExchangeRate-API or hardcoded fallback)

**Output:** Terse, robotic, single emoji per bullet. No instructions or chatter.

**Data Methods** ([src/services/news_data_service.py](../src/services/news_data_service.py)):

- `get_color_of_day()` → Thai lucky color (365-color cycle, 24h cache, no API key needed)
- `get_sunset_sunrise_times()` → Bangkok times from Open-Meteo (24h cache, no API key)
- `get_thai_holidays()` → Uses 'holidays' Python library (7d cache, no API key)
- `get_bitcoin_price()` → CoinGecko free API (5-min cache, volatile data)
- `get_exchange_rates()` → ExchangeRate-API or hardcoded THB rates (1h cache)

**Menu Handlers** ([src/agents/news_agent.py](../src/agents/news_agent.py)):

- `_send_color_sunset_sunrise()` → Item 6 output
- `_send_holidays_markets()` → Item 7 output
- `_send_crypto_exchange()` → Item 8 output
- Thai numerals (๖=6, ๗=7, ๘=8) normalized to Arabic in `_handle_main_menu()`

**Optional API Keys** ([src/config.py](../src/config.py)):

| Service          | Env Variable          | Default | Plan             | Fallback              |
| ---------------- | --------------------- | ------- | ---------------- | --------------------- |
| NewsAPI          | NEWS_API_KEY          | None    | 100 req/day free | Placeholder headlines |
| ExchangeRate-API | EXCHANGE_RATE_API_KEY | None    | 1500 req/mo free | Hardcoded rates (THB) |
| Open-Meteo       | (none needed)         | Free    | Unlimited        | N/A (always works)    |
| CoinGecko        | (none needed)         | Free    | Unlimited        | N/A (always works)    |

**Cache TTLs** ([src/config.py](../src/config.py)):

| Setting                    | Env Variable               | Default | Range        | Purpose                  |
| -------------------------- | -------------------------- | ------- | ------------ | ------------------------ |
| color_cache_ttl_seconds    | COLOR_CACHE_TTL_SECONDS    | 86400   | 3600–86400   | Lucky color (daily)      |
| sunset_cache_ttl_seconds   | SUNSET_CACHE_TTL_SECONDS   | 86400   | 3600–86400   | Sunset/sunrise times     |
| holiday_cache_ttl_seconds  | HOLIDAY_CACHE_TTL_SECONDS  | 604800  | 86400–604800 | Thai holidays (weekly)   |
| bitcoin_cache_ttl_seconds  | BITCOIN_CACHE_TTL_SECONDS  | 300     | 60–3600      | Bitcoin price (volatile) |
| exchange_cache_ttl_seconds | EXCHANGE_CACHE_TTL_SECONDS | 3600    | 300–14400    | Exchange rates (hourly)  |

## �📋 Session & Rate-Limiting Rules (TranslationAgent Only)

All enforced via singletons in [src/services](../src/services):

- **Chat ID format:** `user_<id>`, `group_<id>`, `room_<id>` (normalized in `_get_chat_id()`)
- **Session state** ([src/services/session_manager.py](../src/services/session_manager.py)):
  - `is_session_active(chat_id)` → checks sleep mode + active sessions
  - Sleep mode: `sleep_chat(chat_id, hours=24)` blocks translation; wake: `wake_chat(chat_id)`
  - Dedup: `is_duplicate_message(chat_id, text)` within 60s window (per-chat history)
- **Rate limiting** ([src/services/rate_limiter.py](../src/services/rate_limiter.py)):
  - **Hard limit:** 10 requests / 60 seconds per chat
  - Returns `429` if breached; respects `Retry-After` headers from translation APIs

## 🌐 Translation Provider Stack

**Shared HTTP client** (singleton `httpx.AsyncClient`) created in [src/main.py](../src/main.py):

1. **Primary:** Google Translate ([src/services/google_translation.py](../src/services/google_translation.py))
   - Async with automatic retry (`with_retry()`) controlled by `settings.translation_max_retries`
   - Used by `TranslationAgent.translate()`
2. **Fallback:** LibreTranslate ([src/services/translation_service.py](../src/services/translation_service.py))
   - Public instance (https://libretranslate.de) or self-hosted
   - Also detects language via `detect_language(text)`

**Do not create multiple `httpx.AsyncClient` instances** — reuse the singleton from context.

## 🛠️ Developer Workflows

```bash
# Local development (requires .env)
python -m uvicorn src.main:app --reload --port 8000

# Docker (see docker-compose.yml)
docker-compose up --build

# Testing (pytest with asyncio support; see pytest.ini)
pytest                                    # Run all
pytest --cov=src --cov-report=html       # With coverage
pytest tests/test_translation_agent.py    # Single file
```

## ➕ Adding a New Agent (Pattern)

1. **Create** `src/agents/<your_agent>.py` and subclass `BaseAgent`
2. **Implement:**
   - `async def should_handle(event, text) -> bool` — return True if this agent matches
   - `async def handle(event, text, line_bot_api) -> bool` — return True if successful
   - `get_priority() -> int` — return 0-100 (lower = runs first)
3. **Pick priority wisely:**
   - `<10`: Preempts translation (rarely needed; AdminAgent is exception at 5)
   - `10-20`: Runs after translation checks
   - `>20`: Fallback behavior
4. **Register in `src/main.py` lifespan:**
   ```python
   @asynccontextmanager
   async def lifespan(app: FastAPI):
       # ... existing setup ...
       agent_router.register_agent(YourAgent(settings, client))
       yield
   ```

## 📝 Code Patterns to Follow

- **Logging:** Always use `logger = logging.getLogger(__name__)` at module level; prefix messages with emoji (✅ success, ❌ error, 🔍 debug, ⚠️ warning)
- **Tracing:** Import `get_tracer(__name__)` from `src/utils/tracing`; wrap agent logic in `tracer.start_as_current_span()`
- **Error handling:** Catch `linebot.v3.exceptions.ApiException` and `httpx.TimeoutException` separately; log before rethrowing or responding with fallback
- **Chat ID extraction:** Use `_get_chat_id(event)` pattern (see `TranslationAgent` & `NewsAgent` for examples)
- **Environment variables:** Load from `src/config.py` settings singleton; never hardcode secrets
- **Friend gating** (NewsAgent pattern):

  ```python
  def _is_group_chat(self, event: MessageEvent) -> bool:
      """Check if message is from group or room."""
      return bool(getattr(event.source, "group_id", None) or getattr(event.source, "room_id", None))

  async def _is_friend(self, event: MessageEvent, line_bot_api: MessagingApi) -> bool:
      """Verify friendship via LINE API; returns False if non-friend or error."""
      try:
          line_bot_api.get_profile(getattr(event.source, "user_id", None))
          return True
      except ApiException:
          return False
  ```

## ⚠️ Known Gotchas & Legacy

- **Do not edit** [src/handlers/message_handler.py](../src/handlers/message_handler.py) (older Flex-message handler) unless a test explicitly requires it — production uses agent routing
- **Self-message loop prevention:** Check `event.source.user_id == bot_user_id` before processing (done in webhook handler)
- **Async-only code:** No `time.sleep()`, no blocking I/O — use `await asyncio.sleep()` and async libraries
- **LINE SDK v3:** Uses `linebot.v3.webhooks` and `linebot.v3.messaging`; avoid v2 imports
- **NewsAgent access control:** Friend gating enforced via LINE API `get_profile()` call; non-friends and private chats fallback to trigger translation only. No menu/data shown outside eligible contexts.
- **NewsAgent multi-step flow:** Uses `news_session_manager` to track conversation state; test thoroughly if modifying state transitions. Output is terse (robotic): single emoji per bullet, no instructions or explanations.
