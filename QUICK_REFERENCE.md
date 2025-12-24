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
```

## 🤖 Agent Priority Order

1. **AdminAgent** (Priority 5) - `/admin` commands
2. **TranslationAgent** (Priority 10) - Thai ↔ English translation
3. **NewsAgent** (Priority 15) - `news` or `ข่าว` trigger

## ⏱️ Rate Limits

| Agent           | User Type          | Limit            | Time Window           |
| --------------- | ------------------ | ---------------- | --------------------- |
| **Translation** | Admin              | Unlimited        | -                     |
| **Translation** | Standard           | 10 requests      | 60 seconds            |
| **News**        | Admin              | Unlimited        | -                     |
| **News**        | Friend (group)     | 1 request        | 3600 seconds (1 hour) |
| **News**        | Non-friend (group) | Translation only | -                     |
| **News**        | Private chat       | Translation only | -                     |

## 📰 News Agent Access Matrix

| Context    | User Type  | Trigger          | Response         |
| ---------- | ---------- | ---------------- | ---------------- |
| Group/Room | Friend     | `news` or `ข่าว` | Full 8-item menu |
| Group/Room | Non-friend | `news` or `ข่าว` | Translation only |
| Private    | Any        | `news` or `ข่าว` | Translation only |

## 🛠️ Admin Commands

```
/admin status          - Show bot status
/admin sleep [hours]   - Put chat to sleep
/admin wake            - Wake up chat
/admin reset           - Reset rate limiter
/admin stats           - View session stats
```

## 📋 Translation Features

- ✅ Auto-detect Thai/English
- ✅ Incomplete sentence detection (prevents hallucination)
- ✅ Parentheses preservation: `(Name)` stays as `(Name)`
- ✅ Session management per chat
- ✅ Sleep mode: "amen" → 24h sleep
- ✅ Wake command: "TeacherBoy" alone

## 📰 News Menu (Friends in Groups/Rooms)

1. 🌡️💨 Weather & Air Quality
2. 🌧️ Rain Forecast (5 hours)
3. 📅 Next Holiday (inline)
4. 📈 Indices (inline)
5. ₿ Crypto (BTC, ETH, USDT) (inline)
6. 💱 Exchange Rates (inline)
7. 📰 Headlines (Top 5, pick 1-5)

## 🔍 Key File Locations

```
src/
├── main.py                    # FastAPI entry point
├── config.py                  # Settings & environment
├── agents/
│   ├── agent_router.py        # Agent dispatch
│   ├── base_agent.py          # Abstract base
│   ├── translation_agent.py   # Translation logic
│   ├── news_agent.py          # News logic
│   └── admin_agent.py         # Admin commands
├── services/
│   ├── translation_service.py      # LibreTranslate
│   ├── google_translation.py       # Google Translate
│   ├── news_data_service.py        # News/weather data
│   ├── session_manager.py          # Chat sessions
│   ├── rate_limiter.py             # Rate limiting
│   └── news_session_manager.py     # News flow state
└── utils/
    ├── text_preprocessing.py       # Incomplete detection
    └── tracing.py                  # OpenTelemetry
```

## 🐛 Common Issues & Solutions

| Issue                   | Solution                                   |
| ----------------------- | ------------------------------------------ |
| Translation not working | Check `GOOGLE_TRANSLATE_API_KEY` in `.env` |
| News menu not showing   | Verify user is friend and in group chat    |
| Rate limited            | Wait for time window or use admin account  |
| Bot not responding      | Check LINE webhook URL configuration       |
| Incomplete translation  | Fixed in v3.1.0+ with ellipsis append      |

## 📊 Testing Commands

```bash
# Run specific test files
pytest tests/test_translation_agent.py
pytest tests/test_news_agent.py
pytest tests/test_incomplete_sentence_detection.py

# Run with verbose output
pytest -v

# Run with coverage
pytest --cov=src --cov-report=term-missing
```

## 🔗 Important URLs

- **LINE Developers Console:** https://developers.line.biz/console/
- **Google Cloud Console:** https://console.cloud.google.com/
- **Hugging Face Spaces:** https://huggingface.co/spaces/EvilEvan/TeacherBOY
- **GitHub Repository:** https://github.com/TeacherEvan/TeacherBOY

## 📝 Development Workflow

1. **Make changes** to source files
2. **Run tests:** `pytest`
3. **Check errors:** `get_errors` tool
4. **Commit changes:** `git add -A && git commit -m "..."`
5. **Deploy:** `git push origin main && git push hf main`
6. **Monitor:** Check Hugging Face logs (2-3 min rebuild)

## 🎯 Best Practices

### Code Patterns

- Use `async def` for all agent methods
- Import `get_tracer(__name__)` for OpenTelemetry
- Log with emoji prefixes: ✅ success, ❌ error, 🔍 debug
- Extract chat ID with `_get_chat_id(event)` pattern
- Check admin with `_is_admin(user_id)` before bypassing limits

### Rate Limiting

- Always check admin status first
- Log admin bypasses for monitoring
- Show remaining requests in rate limit messages
- Use per-chat rate tracking (not per-user)

### Translation

- Detect incomplete sentences before translation
- Preserve text in parentheses
- Use Google Translate as primary, LibreTranslate as fallback
- Include context in error logs

## 📖 Documentation

- **Complete Index:** [DOCUMENTATION_INDEX.md](DOCUMENTATION_INDEX.md)
- **Changelog:** [CHANGELOG.md](CHANGELOG.md)
- **Architecture:** [ARCHITECTURE.md](ARCHITECTURE.md)
- **AI Coding Guide:** [.github/copilot-instructions.md](.github/copilot-instructions.md)

## 🆘 Getting Help

1. Check [DOCUMENTATION_INDEX.md](DOCUMENTATION_INDEX.md) for relevant docs
2. Review [CHANGELOG.md](CHANGELOG.md) for recent changes
3. Search issues on GitHub
4. Check [.github/copilot-instructions.md](.github/copilot-instructions.md) for coding patterns

---

**Version:** 3.2.0  
**Last Updated:** 2025-12-16  
**Status:** Production Ready ✅
