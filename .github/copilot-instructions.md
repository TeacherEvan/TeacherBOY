# GitHub Copilot Instructions for TeacherBOY

## Project Overview

TeacherBOY is a **production-grade LINE bot for automatic Thai/English translation** with intelligent session management.

**Primary Purpose: Translation**
- Auto-start translation when Thai text detected
- Session-based continuous translation mode with sleep/wake commands  
- Rate limiting (10 translations/min) and deduplication (60s window)
- Supports 1-on-1 chats, groups, and multi-person conversations
- Google Cloud Translation API (primary) + LibreTranslate (fallback)

**Architecture:** Multi-agent system allows extensibility, but translation is the core feature.

**Critical Design Pattern:** Agent-based routing with priority system - messages flow through `AgentRouter` to appropriate agent based on trigger patterns and priority.

## Tech Stack

- **Python 3.11** + **FastAPI** with full async/await
- **LINE Bot SDK v3** (webhooks + messaging API)
- **Google Cloud Translation API** (primary) + **LibreTranslate** (fallback)
- **APScheduler** (background tasks), **langdetect** (language detection)
- **httpx** with HTTP/2 and connection pooling
- **Pydantic Settings** for type-safe configuration
- **Docker** + **Docker Compose** for deployment

## Architecture: Multi-Agent System

### Agent Flow (Priority-Based Routing)
```
LINE Webhook → FastAPI /webhook → Signature Verification
  → AgentRouter.route_message() → Iterates agents by priority
    → agent.should_handle() → First match → agent.handle()
```

### Key Components

**1. Agent System** (`src/agents/`)
- `base_agent.py`: Abstract base with `should_handle()`, `handle()`, `get_priority()`, `enable/disable()`
- `agent_router.py`: Routes to first matching agent (sorted by priority, lower = higher)
- `translation_agent.py`: **PRIMARY AGENT** - Priority 10, triggers on Thai text OR active session
- `calendar_agent.py`: ⚠️ FROZEN/DEPRECATED - Optional scheduler, not core functionality

**2. Application Lifecycle** (`src/main.py`)
- FastAPI `lifespan` context manager handles startup/shutdown
- Phase 1: Bot identity detection (prevents infinite loops)
- Phase 2: HTTP client pool + translation services init
- Phase 3: Agent registration (translation agent is primary)
- Phase 4: Graceful shutdown (closes HTTP client)

**3. Services** (`src/services/`)
- `translation_service.py`: LibreTranslate integration with `detect_language()` and `translate()`
- `google_translation.py`: Google Cloud Translation API (preferred)
- `session_manager.py`: Chat-level state (active sessions, sleep mode, deduplication)
- `rate_limiter.py`: Per-chat request limiting (10/min default)
- `scheduler_service.py`: APScheduler wrapper for timed jobs

**4. Configuration** (`src/config.py`)
- Pydantic Settings with validation
- All config from environment variables
- Type-safe with defaults and constraints
- Agent registration and scheduler setup
- Health check and test endpoints

## Critical Patterns & Conventions

### 1. Translation Agent Session Management
**Pattern:** State machine with 3 modes per chat
- **Inactive:** Bot ignores messages until Thai text detected or "TeacherBoy" said
- **Active:** Translates EVERY message (Thai→EN, EN→TH)
- **Sleeping:** 24hr timeout after "Thank you TeacherBoy" - ignores all messages

**Implementation:**
```python
# SessionManager tracks per-chat state (src/services/session_manager.py)
session_manager.is_session_active(chat_id)  # Check active
session_manager.is_sleeping(chat_id)        # Check sleeping
session_manager.sleep_chat(chat_id, hours=24)  # Enter sleep
```

### 2. Message Deduplication (Critical for LINE)
**Why:** LINE webhooks sometimes deliver duplicate messages within seconds

**Pattern:** Hash-based deduplication with 60s window
```python
# In SessionManager
message_hash = hashlib.sha256(f"{chat_id}:{user_id}:{text}".encode()).hexdigest()[:16]
if message_hash in recent_hashes:  # Skip duplicate
    return False
```

### 3. Rate Limiting (Prevent API Quota Exhaustion)
**Pattern:** Per-chat sliding window (10 requests/60s)
```python
# Check before translation
if not rate_limiter.is_allowed(chat_id):
    # Send rate limit message to user
    remaining_seconds = rate_limiter.get_reset_time(chat_id)
```

### 4. Bot Self-Message Detection (Prevent Infinite Loops)
**Critical:** Bot fetches its own `user_id` during startup and NEVER responds to its own messages
```python
# In main.py lifespan
bot_info = line_bot_api.get_bot_info()
bot_user_id = bot_info.user_id

# In webhook handler
if event.source.user_id == bot_user_id:
    return  # Skip self-messages
```

### 5. HTTP Client Connection Pooling
**Pattern:** Single global `httpx.AsyncClient` with HTTP/2 + keep-alive
```python
# Created once in lifespan, shared by all services
http_client = httpx.AsyncClient(
    timeout=30, 
    limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
    http2=True
)
translation_service.set_client(http_client)
```

### 6. Agent Priority System
**Rule:** Lower number = higher priority. Translation agent is THE primary agent.
- **Translation: Priority 10** (core feature, handles all translation requests)
- Custom agents: Use priority 15, 20, 25, etc. for additional features
- Never create agents that interfere with translation workflow

## Development Workflows

### Running Locally
```bash
# Preferred: Docker (consistent environment)
docker-compose up --build

# Direct Python (for debugging)
python -m uvicorn src.main:app --reload --port 8000
```

### Testing
```bash
# Run all tests with coverage
pytest --cov=src --cov-report=html

# Run specific test file
pytest tests/test_translation_service.py -v

# Test async functions
pytest tests/test_translation_service.py::TestTranslationService::test_auto_translate_thai_to_english
```

**Test Patterns:**
- Mock `httpx.AsyncClient` for external API calls
- Use `@pytest.mark.asyncio` for async tests
- `pytest.ini` configures `asyncio_mode = auto`

### Adding a New Agent
1. **Create agent class** inheriting from `BaseAgent`:
   ```python
   class MathAgent(BaseAgent):
       def __init__(self):
           super().__init__(name="MathAgent", description="Solves math problems")
       
       def get_priority(self) -> int:
           return 15  # Between Translation (10) and Calendar (20)
       
       async def should_handle(self, event, text) -> bool:
           return text.startswith("calc:") or "solve:" in text.lower()
       
       async def handle(self, event, text, line_bot_api) -> bool:
           # Process and reply
           pass
   ```

2. **Register in `main.py` lifespan**:
   ```python
   math_agent = MathAgent()
   agent_router.register_agent(math_agent)
   ```

3. **Add tests** in `tests/test_math_agent.py`

### LINE Webhook Setup (ngrok for local testing)
```bash
# Terminal 1: Run bot
docker-compose up

# Terminal 2: Expose with ngrok
ngrok http 8000

# Copy HTTPS URL (e.g., https://abc123.ngrok.io)
# Set in LINE Developers Console: https://abc123.ngrok.io/webhook
```

### Environment Variables
**Required:**
- `LINE_CHANNEL_SECRET` - For webhook signature verification
- `LINE_CHANNEL_ACCESS_TOKEN` - For sending messages

**Recommended:**
- `GOOGLE_TRANSLATE_API_KEY` - Much better quality than LibreTranslate

**Optional:**
- `DEBUG=True` - Enable FastAPI /docs endpoint and verbose logging

## Coding Standards (Project-Specific)

### Async Everywhere
**Pattern:** All I/O operations MUST be async (LINE API, translation APIs, HTTP calls)
```python
# ✅ Correct
async def handle(self, event, text, line_bot_api):
    translation = await translation_service.translate(text, "th", "en")

# ❌ Wrong (blocks event loop)
def handle(self, event, text, line_bot_api):
    translation = translation_service.translate_sync(text, "th", "en")
```

### Error Handling with User Feedback
**Pattern:** Always catch exceptions and send user-friendly LINE messages
```python
try:
    translation = await google_translation_service.translate(text, "th", "en")
except Exception as e:
    logger.error(f"Translation failed: {e}", exc_info=True)
    await line_bot_api.reply_message_async(
        ReplyMessageRequest(
            reply_token=event.reply_token,
            messages=[TextMessage(text="⚠️ Translation temporarily unavailable")]
        )
    )
    return False
```

### Logging Conventions
- `logger.info()` - State changes, agent actions, successful operations
- `logger.warning()` - Rate limits, sleep mode, non-critical issues
- `logger.error()` - API failures, exceptions (with `exc_info=True`)
- `logger.debug()` - Detailed flow (enabled via `DEBUG=True`)

**Never log:** User message content (privacy), API keys, LINE tokens

### Pydantic Validation for Config
**Pattern:** All config uses Pydantic with constraints and defaults
```python
class Settings(BaseSettings):
    line_channel_secret: str = Field(min_length=10, description="...")
    rate_limit_max: int = Field(default=10, ge=1, le=100)  # 1-100 range
```

## Common Pitfalls & Solutions

### Pitfall 1: Infinite Message Loops
**Problem:** Bot responds to its own messages → triggers itself again
**Solution:** Fetch `bot_user_id` at startup and skip self-messages (already implemented in `main.py`)

### Pitfall 2: Duplicate Message Processing
**Problem:** LINE webhooks occasionally send duplicates
**Solution:** Use `SessionManager` deduplication (60s hash-based window)

### Pitfall 3: Agent Order Matters
**Problem:** Translation agent catches all messages before other agents run
**Solution:** Use priority system - specific agents at lower priority (5-9), translation at 10

### Pitfall 4: Blocking I/O in Async Context
**Problem:** Using `requests` or sync libraries blocks the event loop
**Solution:** Use `httpx.AsyncClient` for all HTTP calls, `await` all I/O

### Pitfall 5: Rate Limit Confusion
**Problem:** Users hit API quotas and get no feedback
**Solution:** Check `rate_limiter.is_allowed()` before translation, send specific error message

## Key Documentation Files
- `ARCHITECTURE.md` - Detailed webhook flow and component explanations
- `QUICK_START.md` - Google Translate API setup (HIGHLY RECOMMENDED)
- `docs/LINE_SETUP.md` - Getting LINE credentials and webhook config
- `MULTI_AGENT_GUIDE.md` - Guide to building custom agents (for extensibility)

---

## ⚠️ FROZEN FEATURES (Do Not Develop)

### Calendar Integration (DEPRECATED)
**Status:** Feature frozen until further notice. Focus is 100% on translation.

- `calendar_agent.py` exists but is NOT the primary feature
- `GOOGLE_CALENDAR_GROUP_ID` env var is optional and should be ignored
- Scheduler setup in `main.py` is legacy code
- If asked about calendar features, redirect focus to translation capabilities

**Why frozen:** TeacherBOY is a **translation bot**, not a calendar bot. Calendar was an experimental feature that distracted from the core mission.
