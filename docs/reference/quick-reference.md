# Ms. Green Quick Reference Card

> **Essential information at a glance**

## 🚀 Quick Start Commands

```bash
# Local development
python -m uvicorn src.main:app --reload --port 8000

# Docker deployment
docker-compose up --build

# Run tests
pytest
pytest --cov=src --cov-report=html

# Deploy to Hugging Face (direct push - GitHub Actions blocked by billing)
git remote add hf https://EvilEvan:${HF_TOKEN}@huggingface.co/spaces/EvilEvan/TeacherBOY
git push hf HEAD:main --force
```

## 🔑 Environment Variables (Required)

```env
LINE_CHANNEL_SECRET=your_channel_secret
LINE_CHANNEL_ACCESS_TOKEN=your_access_token
GITHUB_MODELS_PAT=your_github_models_pat
OPENROUTER_API_KEY=your_openrouter_api_key  # Optional fallback
ADMIN_USER_IDS=U1234567890,U0987654321  # Comma-separated LINE user IDs
MODERATOR_USER_IDS=U1234567890  # Optional: Moderators get direct news access

# Named outbound recipients (admin push)
USER_BOSS=U1234567890abcdef

# Harmful content detection (Moderator Mode)
HARMFUL_CONTENT_KEYWORDS=spam,scam,phishing  # Comma-separated custom keywords
HARMFUL_CONTENT_KEYWORDS_FILE=./config/harmful_keywords.json  # Optional JSON file
```

## 🤖 Agent Priority Order
## 🤖 Agent Priority Order
1. **ModModeAgent** (Priority 4) - Group moderation: `activate mod mode`, `/modmode ...` (intercepts first in mod-enabled groups)
2. **HelpAgent** (Priority 5) - Comprehensive help system (`help`, `Dear Ms. Green help`, etc.)
3. **AdminAgent** (Priority 5) - `/admin` commands
4. **CalendarAgent** (Priority 6) - `Ms. Green calendar`, `Ms. Green add`, `Ms. Green events`
5. **HannibalProfileAgent** (Priority 6) - `hannibal profile`, `analyze messages` - Message-history profiling
6. **ProfilerAgent** (Priority 7) - Image-based psychological profiling
7. **ImageAnalyzerAgent** (Priority 7) - `Ms. Green analyze`, general image Q&A and date extraction
8. **DocumentMemoryAgent** (Priority 8) - `Ms. Green doc`, `Ms. Green docs` - PDF/DOCX storage and retrieval
9. **SearchAgent** (Priority 8) - `Ms. Green search <query>` - Web search via Brave Search API
10. **LLMAgent** (Priority 9) - `Ms. Green <prompt>` - General LLM conversation
11. **TranslationAgent** (Priority 10) - Thai ↔ English translation
12. **SpecialNewsAgent** (Priority 12) - `/special news` command
13. **NewsAgent** (Priority 15) - `news` or `ข่าว` trigger

## 🤖 AI & Search Commands (Ms. Green)

- **AI chat:** `Ms. Green <your question>`
  - **Admins:** allowed in any chat context
  - **Regular users:** available in direct messages; gated in non-private chats

### 📨 Ms. Green outbound messaging (admins)

Requires configuring named recipients:

```env
USER_BOSS=U1234567890abcdef
```

Then:

- `Ms. Green send <alias> <text>`
- `Ms. Green llm_send <alias> <prompt>`
- `Ms. Green send_weather <alias>`
- **Web search (Brave Search):** `Ms. Green search <query>`
  - **Admins:** allowed in any chat context
  - **Regular users:** **DM only** (1-on-1)

Notes:

- `Ms. Green search ...` is handled by SearchAgent before LLMAgent.
- If `OPENROUTER_API_KEY` or `BRAVE_SEARCH_API_KEY` is missing, the bot replies with a configuration error.

## 🚢 Hugging Face Spaces (Docker) gotcha

- Avoid having multiple copies of the code
  (for example both top-level `src/` and nested `TeacherBOY/src/`).
- The container runs `uvicorn src.main:app` from the top-level `src/`,
  so nested code is ignored unless the Dockerfile is updated.

## ⏱️ Rate Limits

| Agent           | User Type          | Limit            | Time Window           |
| --------------- | ------------------ | ---------------- | --------------------- |
| **Translation** | Admin              | Unlimited        | -                     |
| **Translation** | Premium (USER_NAME)| 3 interactions   | 24 hours (daily)      |
| **Translation** | Premium (USER_NAME)| 1 interaction    | 60 seconds (burst)    |
| **Translation** | Standard           | 10 requests      | 60 seconds (chat)     |
| **News**        | Admin/Moderator    | Unlimited        | -                     |
| **News**        | Friend (group)     | 1 request        | 3600 seconds (1 hour) |
| **News**        | Non-friend (group) | Translation only | -                     |
| **News**        | Private chat       | Translation only | -                     |

**Premium Access:** Set `USER_NAME=<LINE_USER_ID>` for authenticated user limits with upgrade messaging.

## 📰 News Agent Access Matrix

<!-- markdownlint-disable MD060 -->

| Context    | User Type       | Trigger          | Response         |
| :--------- | :-------------- | :--------------- | :--------------- |
| Group/Room | Friend          | `news` or `ข่าว` | Full menu        |
| Group/Room | Non-friend      | `news` or `ข่าว` | Translation only |
| Private    | Admin/Moderator | `news` or `ข่าว` | Full menu        |
| Private    | Regular user    | `news` or `ข่าว` | Translation only |

<!-- markdownlint-enable MD060 -->

## 🛠️ Admin Commands

See [ADMIN_COMMANDS.md](../ADMIN_COMMANDS.md) for complete documentation.

Quick summary:
```text
/admin status          - Show bot status
/admin sessions        - List active sessions
/admin groups          - List groups/rooms bot is in
/admin dashboard       - Open DM-first admin dashboard
/admin sleep [hours]   - Put chat to sleep
/admin wake            - Wake up chat
/admin reset           - Reset rate limiter (preview + confirm)
/admin purge           - Purge session state (preview + confirm)
/admin leave           - Leave group/room (preview + confirm)
/admin confirm <token> - Confirm destructive action
/admin cancel <token>  - Cancel destructive action
/admin whoami          - Show your LINE user_id (debug)
/admin send <alias> <text>       - Push to named recipient
/admin llm_send <alias> <prompt> - LLM-drafted push
/admin send_weather <alias>      - Push Bangkok weather
```

## 🛡️ Moderator Mode Commands

See [MODERATOR_MODE.md](../MODERATOR_MODE.md) for complete documentation.

**Activation:** `activate mod mode` (admin only, in group)

Quick summary:
```text
/modmode                    - Show current mode + dashboard
/modmode dashboard          - Open Flex dashboard (quick-reply buttons)
/modmode all                - Switch to ALL mode (open + harmful detection)
/modmode special @user     - Switch to SPECIAL mode (restricted speakers)
/modmode kick @user         - Kick user from group
/modmode warn @user [reason] - Issue manual warning
/modmode ban @user [reason]  - Ban user (adds to ban list + kicks)
/modmode unban @user        - Remove from ban list
/modmode banlist            - Show all banned users in this group
/modmode deactivate         - Disable moderator mode for this group
```

> **Only works in groups where mod mode is active. Only for admins.**

## 📋 Translation Features

- ✅ Auto-detect Thai/English
- ✅ Incomplete sentence detection (prevents hallucination) — [INCOMPLETE_SENTENCE_FIX.md](../INCOMPLETE_SENTENCE_FIX.md)
- ✅ Parentheses preservation: `(Name)` stays as `(Name)`
- ✅ Session management per chat
- ✅ Sleep mode: "Thanks Ms Green!" → 24h sleep
- ✅ Wake command: "Dear Ms. Green" alone

## 📰 News Menu (Friends/Admins/Moderators)

**All data shown inline:**

1. 🌡️💨 Weather & Air Quality - Bangkok temperature + PM2.5
2. 🌧️ Rain Forecast - 5-hour prediction
3. 📅 Next Holiday - Upcoming Thai holiday
4. 📈 Indices - S&P 500, DJIA, FTSE 100
5. ₿ Crypto - BTC, ETH, USDT prices
6. 💱 Exchange Rates - THB→USD, JPY, ZAR, AUD, GBP, RUB
7. 📰 Headlines 1-5 - Thailand news with URLs (select 1-5 for details)

**Special News** (`/special news` in DM):

- 🧳 Tourism News (5 headlines)
- 🏟️ Sports News (5 headlines)
- 🌍 International News (5 headlines)

## 🔍 Key File Locations

```text
src/
├── main.py                    # FastAPI entry point
├── config.py                  # Settings & environment
├── agents/
│   ├── agent_router.py        # Agent dispatch
│   ├── base_agent.py          # Abstract base
│   ├── help_agent.py          # Comprehensive help system
│   ├── calendar_agent.py      # Calendar entry point
│   ├── document_memory_agent.py # PDF/DOCX memory
│   ├── hannibal_agent.py      # Message-history profiling
│   ├── image_analyzer_agent.py # General image Q&A
│   ├── llm_agent.py           # LLM chat (Ms. Green ...)
│   ├── profiler_agent.py      # Image profiling
│   ├── search_agent.py        # Brave Search (Ms. Green search ...)
│   ├── translation_agent.py   # Translation logic
│   ├── news_agent.py          # News logic
│   ├── special_news_agent.py  # Special news (DM-only)
│   └── admin_agent.py         # Admin commands
├── services/
│   ├── openrouter_service.py       # OpenRouter client
│   ├── brave_search_service.py     # Brave Search client
│   ├── ai_translation_service.py   # Shared AI translation orchestration (+ latency metrics)
│   ├── metrics_service.py          # In-memory metrics + provider latency tracking
│   ├── news_data_service.py        # News/weather data
│   ├── special_news_service.py     # Special news RSS
│   ├── calendar_service.py         # Calendar storage
│   ├── conversation_memory_service.py # Chat memory
│   ├── document_memory_service.py  # Document storage
│   ├── session_manager.py          # Translation sessions
│   ├── news_session_manager.py     # News flow state
│   └── rate_limiter.py             # Rate limiting
└── utils/
    ├── text_preprocessing.py       # Parentheses + incomplete detection
    └── tracing.py                  # OpenTelemetry setup

tests/
├── test_translation_agent.py
├── test_news_agent.py
├── test_special_news_agent.py
├── test_admin_agent.py
└── ...
```

## 📊 Cache TTLs (Configurable via .env)

| Data Type      | Default TTL | Env Variable               | Range        |
| -------------- | ----------- | -------------------------- | ------------ |
| Weather        | 30 min      | WEATHER_CACHE_TTL_SECONDS  | 300–7200     |
| News           | 1 hour      | NEWS_CACHE_TTL_SECONDS     | 600–14400    |
| Holidays       | 7 days      | HOLIDAY_CACHE_TTL_SECONDS  | 86400–604800 |
| Bitcoin        | 5 min       | BITCOIN_CACHE_TTL_SECONDS  | 60–3600      |
| Exchange Rates | 1 hour      | EXCHANGE_CACHE_TTL_SECONDS | 300–14400    |

## 🔗 Documentation Links

- **[docs/README.md](../README.md)** - Documentation home
- **[docs/guides/quickstart.md](../guides/quickstart.md)** - Detailed quickstart
- **[docs/guides/line-setup.md](../guides/line-setup.md)** - LINE Bot setup
- **[docs/guides/deployment.md](../guides/deployment.md)** - Deployment guide
- **[docs/ADMIN_COMMANDS.md](../ADMIN_COMMANDS.md)** - Admin reference
- **[docs/TRACING.md](../TRACING.md)** - OpenTelemetry tracing
- **[docs/architecture/agents.md](../architecture/agents.md)** - Agent system
- **[docs/CALENDAR_REMINDERS.md](../CALENDAR_REMINDERS.md)** - Calendar & reminders
- **[docs/IMAGE_ANALYZER.md](../IMAGE_ANALYZER.md)** - Image analyzer (general Q&A)
- **[docs/SEARCH_AGENT.md](../SEARCH_AGENT.md)** - Web search agent
- **[docs/HANNIBAL_PROFILE.md](../HANNIBAL_PROFILE.md)** - Message-history profiling
- **[docs/PROFILER_USAGE.md](../PROFILER_USAGE.md)** - Psychological profiler (image-based)
- **[docs/DOCUMENT_MEMORY.md](../DOCUMENT_MEMORY.md)** - Document memory
- **[docs/NEWS_AGENT.md](../NEWS_AGENT.md)** - News agent
- **[docs/MODERATOR_MODE.md](../MODERATOR_MODE.md)** - Moderator mode
- **[docs/CONVERSATION_MEMORY.md](../CONVERSATION_MEMORY.md)** - Conversation memory
