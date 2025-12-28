# TeacherBOY Quick Reference Card

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

# Deploy to Hugging Face
git push hf main
```

## 🔑 Environment Variables (Required)

```env
LINE_CHANNEL_SECRET=your_channel_secret
LINE_CHANNEL_ACCESS_TOKEN=your_access_token
GOOGLE_TRANSLATE_API_KEY=your_google_api_key  # Optional but recommended
ADMIN_USER_IDS=U1234567890,U0987654321  # Comma-separated LINE user IDs
MODERATOR_USER_IDS=U1234567890  # Optional: Moderators get direct news access

# Optional: named outbound recipients (admin push)
USER_BOSS=U1234567890abcdef
```

## 🤖 Agent Priority Order

1. **AdminAgent** (Priority 5) - `/admin` commands
2. **SearchAgent** (Priority 8) - `Zeus search ...` (DM-only for non-admins)
3. **LLMAgent** (Priority 9) - `Zeus ...` (DM-only for non-admins)
4. **TranslationAgent** (Priority 10) - Thai ↔ English translation
5. **SpecialNewsAgent** (Priority 12) - `/special news` command (DM-only)
6. **NewsAgent** (Priority 15) - `news` or `ข่าว` trigger

## 🤖 AI & Search Commands (Zeus)

- **AI (OpenRouter LLM):** `Zeus <your question>` (also accepts `/zeus ...`, typo `Zues ...`)
  - **Admins:** allowed in any chat context
  - **Regular users:** **admin-only** (denied everywhere)
- **Web search (Brave Search):** `Zeus search <query>` (also accepts `/zeus search ...`, typo `Zues search ...`)
  - **Admins:** allowed in any chat context
  - **Regular users:** **DM only** (1-on-1)

Notes:

- `Zeus search ...` is handled by SearchAgent before LLMAgent.
- If `OPENROUTER_API_KEY` or `BRAVE_SEARCH_API_KEY` is missing, the bot replies with a configuration error.

## 🚢 Hugging Face Spaces (Docker) gotcha

- Avoid having multiple copies of the code (e.g., both top-level `src/` and nested `TeacherBOY/src/`). The container runs `uvicorn src.main:app` from the top-level `src/`, so nested code will be ignored unless the Dockerfile is updated.

## ⏱️ Rate Limits

| Agent           | User Type          | Limit            | Time Window           |
| --------------- | ------------------ | ---------------- | --------------------- |
| **Translation** | Admin              | Unlimited        | -                     |
| **Translation** | Standard           | 10 requests      | 60 seconds            |
| **News**        | Admin/Moderator    | Unlimited        | -                     |
| **News**        | Friend (group)     | 1 request        | 3600 seconds (1 hour) |
| **News**        | Non-friend (group) | Translation only | -                     |
| **News**        | Private chat       | Translation only | -                     |

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

```text
/admin status          - Show bot status
/admin sleep [hours]   - Put chat to sleep
/admin wake            - Wake up chat
/admin reset           - Reset rate limiter
/admin stats           - View session stats (includes tourism news)
/admin send            - Push text to USER_<ALIAS>
/admin llm_send        - Draft via LLM then push
/admin send_weather    - Push Bangkok weather
/admin whoami          - Show your LINE user_id (debug)
```

## 📋 Translation Features

- ✅ Auto-detect Thai/English
- ✅ Incomplete sentence detection (prevents hallucination)
- ✅ Parentheses preservation: `(Name)` stays as `(Name)`
- ✅ Session management per chat
- ✅ Sleep mode: "amen" → 24h sleep
- ✅ Wake command: "TeacherBoy" alone

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
│   ├── llm_agent.py           # OpenRouter LLM (Zeus ...)
│   ├── search_agent.py        # Brave Search (Zeus search ...)
│   ├── translation_agent.py   # Translation logic
│   ├── news_agent.py          # News logic
│   ├── special_news_agent.py  # Special news (DM-only)
│   └── admin_agent.py         # Admin commands
├── services/
│   ├── openrouter_service.py       # OpenRouter client
│   ├── brave_search_service.py     # Brave Search client
│   ├── translation_service.py      # LibreTranslate
│   ├── google_translation.py       # Google Translate
│   ├── news_data_service.py        # News/weather data
│   ├── special_news_service.py     # Special news RSS
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
└── ... (218 tests total)
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
