---
title: Ms. Green
emoji: 👨‍🏫
colorFrom: blue
colorTo: green
sdk: docker
app_port: 8000
---

## Ms. Green 👨‍🏫

> **Repository note:** The repository is still named **TeacherBOY**, but the
> public bot identity and documentation target are now **Ms. Green**.

**Runtime-configurable staff assistant with explicit AI review, DM follow-up, and multi-agent LINE workflows.**

Ms. Green is a high-performance, asynchronous LINE Bot featuring a modular
multi-agent system. The default runtime identity is now `Ms. Green`, with
explicit review flows layered on top of calendar, search, LLM, image, and news
features.

## 📚 Documentation

### Quick Links

- **[📚 Docs Home](docs/README.md)** - Start here (quickstart, deployment, LINE setup, admin)
- **[⚡ Quick Start](docs/guides/quickstart.md)**
- **[⚙️ LINE Setup](docs/guides/line-setup.md)**
- **[🚀 Deployment](docs/guides/deployment.md)**
- **[🏗️ Architecture](docs/architecture/overview.md)**
- **[🤖 Agents](docs/architecture/agents.md)**
- **[🔧 Admin Commands](docs/ADMIN_COMMANDS.md)**
- **[🏫 KPS Assistant](docs/KPS_ASSISTANT.md)**
- **[🔎 Tracing](docs/TRACING.md)**
- **[🛠️ Maintainer Notes](docs/reference/maintainers.md)**
- **[🧭 Environment Reference](docs/reference/environment.md)**

The `docs/` folder is the maintained documentation source of truth.

## 🗂️ Persistence Model

Ms. Green uses mounted local paths for filesystem state and separate Hugging
Face dataset repositories for optional cloud persistence.

- `CONVERSATION_STORAGE_PATH` is the local working/cache directory for HF-backed
  conversation sync; restart persistence still depends on `HF_MEMORY_TOKEN`
  and `HF_MEMORY_REPO_ID`.
- `BOT_IDENTITY_STORAGE_PATH` stores runtime identity overrides.
- `STAFF_MEMORY_STORAGE_PATH` stores review-agent staff memory.
- Scheduled jobs remain runtime-only; there is no persisted APScheduler task store in the current implementation.

For the full variable reference and mounted-volume examples, see [Environment variables](docs/reference/environment.md).

## 🚀 Features

### Ms. Green Review Flow

- **🪪 Runtime Identity:** Display name and aliases are persisted across restarts
- **📝 Explicit Review:** `Ms. Green review` translates and summarizes the last recent non-English message on request only
- **📨 DM Follow-Up:** Review results go directly to the requesting user
- **📌 Weekly Summary:** `Ms. Green what's important this week?` combines calendar items and structured staff memory
- **🤝 Staff Framing:** `Ms. Green who do you work for?` returns the fixed staff-assistant answer

### Translation Agent (Primary)

- **🔥 Smart Auto-Detection:** Automatically starts when Thai text is detected
- **🔄 Continuous Mode:** Translates EVERY message until you say "Thanks Ms Green!"
- **😴 Sleep Mode:** Bot sleeps for 24 hours - say "Dear Ms. Green" alone to wake up
- **🌐 AI Translation:** Shared AI translation service with GitHub Models first and OpenRouter fallback
- **🛡️ Hallucination Prevention:** Detects incomplete sentences and prevents unwanted context injection
- **💬 Bi-directional:** Thai 🇹🇭 → English 🇬🇧 and English 🇬🇧 → Thai 🇹🇭
- **👥 Group Chat Support:** Works in 1-on-1, groups, and multi-person chats
- **📝 Text-Only Responses:** Clean, simple text translations (no distracting cards)
- **🤫 Silent Join:** Bot joins groups silently - only speaks when Thai is detected
- **👋 Welcome Message:** Sends "Welcome friend / ยินดีต้อนรับเพื่อน" when added as friend
- **🎯 Session Management:** Independent sessions per chat
- **📋 Parentheses Preservation:** Names and notes in (parentheses) are never translated
- **⏱️ Rate Limiting:** 10 requests per minute for normal translation traffic; destructive admin requests are limited to 3 per 10 minutes per admin

### News Agent **NEW!**

- **📰 Real-time News:** Bangkok weather, air quality, PM2.5, and Thai news headlines
- **🌡️ Weather Data:** Temperature and 5-hour rain forecast via Open-Meteo
  (no API key for non-commercial use; subject to Open-Meteo terms)
- **💨 Air Quality:** PM2.5 levels for Bangkok
- **📱 Auto-Language Detection:** Type "news" for English or "ข่าว" for Thai
- **🔒 Friend-Gated Access:** Full menu for friends in groups (1 request/hour), translation only for others
- **👑 Admin & Moderator Access:**
  - **Admins:** Unlimited news requests + full admin commands
  - **Moderators:** Direct news access in all contexts (private + groups), bypass rate limits
    - Regular users get trigger translation only in private chats
- **📊 Extended Data:** Thai holidays, market indices, crypto prices, exchange rates
- **🌍 Bilingual:** Full Thai and English support
- **🔗 Inline URLs:** Top 5 headlines displayed with clickable links directly in menu
- **📲 Interactive Details:** Select 1-5 to see full article information
- **⏰ Smart Caching:** 30-min weather, 2-hour news/exchange, 5-min crypto, 7-day holidays (reduces API calls)
- **Trigger:** Type `news` or `ข่าว` to start
- **📰 Special News:** `/special news` in DM provides interactive carousel with tourism, sports, international headlines

### Ms. Green AI (LLM Agent) **NEW!**

- **🤖 Ask Ms. Green:** `Ms. Green <question>`
- **🌡️ Warmth (Temperature):** Configure via `LLM_TEMPERATURE` (default: `1.0`)
- **🧊 Wise Persona (Default):** Controlled by `LLM_SYSTEM_PROMPT` (optional override); calm, gentle, and exceptionally wise, without fairy-tale styling
- **👥 Group Access Policy:**
  - Admins can use Ms. Green anywhere
  - Non-admins follow `ZEUS_GROUP_ACCESS_MODE`:
    - `all` (default)
    - `allowlist` with `ZEUS_ALLOWED_GROUP_IDS`
    - `denylist` with `ZEUS_DENIED_GROUP_IDS`
- **🧑‍💼 Boss Easter Egg:** If asked “who is boss”, replies with exactly: `Evan...`

### Psychological Profiler **NEW!**

- **🔬 FBI/Ekman/Navarro Frameworks:** Professional behavioral analysis
- **📸 Trigger-Based:** Send `Ms. Green profile` then your image
- **🎨 Fictional Artwork Support:** Analyze anime, manga, pencil drawings, concept art
- **♿ Accessibility:** Helps neurodivergent users (autism) understand character expressions
- **🎬 Creative Projects:** Art direction for music videos, storytelling, visual narratives
- **⏱️ Rate Limiting:** 3 analyses/hour (admins unlimited)
- **🤖 Vision AI:** GPT-4o multimodal analysis
- **Full Documentation:** [Profiler Usage Guide](docs/PROFILER_USAGE.md)

### Image Analyzer **NEW!**

- **🖼️ General Image Q&A:** Ask Ms. Green questions about any image
- **🔄 Multi-Step Flow:**
  1. Trigger: `Ms. Green analyze this` / `analyze image` / `examine this`
  2. Ms. Green asks for the image (60 seconds timeout)
  3. Send your image
  4. Ms. Green asks what you want to know
  5. Get your answer from GPT-4o vision
- **💡 Use Cases:**
  - Menu translation: "What would be most enjoyable on this menu to a westerner?"
  - Sign reading: "What does this sign say?"
  - Product identification: "What products are shown here?"
  - Any visual question about the image
- **⏱️ Rate Limiting:** 5 analyses/hour (admins unlimited)
- **🧠 Powered by:** GPT-4o vision via GitHub Models

### Multi-Agent Architecture

- **🏗️ Modular Design:** Easy to add agents with different capabilities
- **⚡ Smart Routing:** Messages routed to appropriate agent by priority
- **🔌 Extensible:** Add math solver, code review, quiz agents, and more!
- **🎨 Clean API:** Simple `BaseAgent` class to inherit from
- **📊 Priority System:** Control which agent handles messages first
- **🔧 Admin Commands:** In-chat control commands for authorized admins
- **📊 Admin Stats:** Enhanced dashboard with current tourism news headlines
- **💭 Conversation Memory:** Multi-turn context for the Ms. Green LLM agent with optional HF Hub persistence **NEW!**
- **📜 History Logging:** Comprehensive audit trail with encryption and cloud backup **NEW!**

### Structured Persistence

- **🧱 Optional Convex Backend:** Set `PERSISTENCE_BACKEND=convex` to make Convex the primary structured persistence backend.
- **🗓️ Calendar + Reminders:** Calendar events and reminder state can now persist through Convex when selected as primary.
- **📝 Review Staff Memory:** Review-agent staff memory can now persist through Convex when selected as primary.
- **⚙️ Future Admin Settings Target:** The admin-only config window is not implemented yet, but Convex `appSettings` is now the intended persistence target for that work.
- **↩️ Rollback Path:** Set `PERSISTENCE_BACKEND=local` and restart the app to return to the local/HF-backed runtime path.

### Performance & Scalability

- **High Performance:** Built on **FastAPI** with full async support
- **Connection Pooling:** Efficient HTTP client management
- **Docker-Ready:** Easy deployment and scaling
- **Stateless:** Horizontal scaling support

## 🛠️ Tech Stack

- **Framework:** Python 3.11+, FastAPI
- **Platform:** LINE Messaging API v3 (Async)
- **Translation:** Shared AI translation service backed by GitHub Models and OpenRouter
- **Architecture:** Multi-agent system with modular design
- **Libraries:** `line-bot-sdk`, `httpx`, `pydantic`

## ⚙️ Quick Start

### 1. Get LINE Tokens

See **[LINE Setup Guide](docs/guides/line-setup.md)** for detailed instructions.

**Already have tokens?** Create a `.env` file:

```env
# Primary Agent - Ms. Green
LINE_CHANNEL_SECRET=your_channel_secret
LINE_CHANNEL_ACCESS_TOKEN=your_channel_access_token

# AI translation providers
GITHUB_MODELS_PAT=your_github_models_pat
OPENROUTER_API_KEY=your_openrouter_api_key  # Optional fallback

# Structured persistence backend
PERSISTENCE_BACKEND=local  # set to convex to use Convex as primary
CONVEX_DEPLOYMENT_URL=
CONVEX_SYNC_TOKEN=
CONVEX_REQUEST_TIMEOUT_SECONDS=10
# Optional: require Convex health before readiness turns green
CONVEX_REQUIRE_HEALTHCHECK_ON_STARTUP=false

# News Agent (optional)
# NEWS_API_KEY is deprecated (headlines use RSS feeds; no key required)
# NEWS_API_KEY=

# Optional: Additional agents
ADDITIONAL_AGENTS=

# Ms. Green AI (optional)
LLM_TEMPERATURE=1.0
# Group/room policy for non-admin Ms. Green usage: all|allowlist|denylist
ZEUS_GROUP_ACCESS_MODE=all
ZEUS_ALLOWED_GROUP_IDS=
ZEUS_DENIED_GROUP_IDS=
# Optional: override Ms. Green persona
# LLM_SYSTEM_PROMPT=

# Admin Control (for bot management)
ADMIN_USER_IDS=

# Optional: named recipients for admin push messaging
# Format: USER_<ALIAS>=<LINE_USER_ID>
USER_BOSS=

DEBUG=False
```

When `PERSISTENCE_BACKEND=convex`, the runtime uses Convex for structured calendar and staff-memory persistence. If you need to roll back quickly, change it back to `local` and restart the service.

### 2. Run Locally

```bash
# With Docker (recommended)
docker build -t ms-green-assistant .
docker run --env-file .env -p 8000:8000 ms-green-assistant

# Or with Python directly
pip install -r requirements.txt
uvicorn src.main:app --host 0.0.0.0 --port 8000
```

### 3. Expose to Internet

```bash
# Use ngrok for testing
ngrok http 8000
# Copy the HTTPS URL (e.g., https://abc123.ngrok.io)
```

### 4. Configure LINE Webhook

1. Go to [LINE Developers Console](https://developers.line.biz/console/)
2. Select your channel → Messaging API tab
3. Set Webhook URL: `https://your-ngrok-url.ngrok.io/webhook`
4. Click **Verify** (should show success)
5. Disable auto-reply in Response settings

### 5. Test

- Scan QR code to add bot
- Send: `สวัสดีครับ` → Translation mode starts! 🔥
- Send: `Hello` → Translates to Thai automatically
- Send: `How are you?` → Keeps translating
- Say: `Thanks Ms Green!` → Bot sleeps for 24 hours 😴
- Say: `Dear Ms. Green` → Bot wakes up! ☀️

**The bot will translate EVERY message until you say "Thanks Ms Green!"!**

**Need help?** See **[Quick Start Guide](docs/guides/quickstart.md)** or **[Deployment Guide](docs/guides/deployment.md)**.

### 6. Admin & Moderator Setup (Optional)

For bot management and privileged access, Ms. Green supports two levels:

**Admin Users (Full Control):**

- `/admin` commands for bot management (status, sleep, wake, reset, etc.)
- Bypass standard translation/news rate limits; destructive admin requests are limited to 3 per 10 minutes per admin
- Direct news access without translation

**Moderator Users (News Access):**

- Direct news access in all contexts (private chats + groups)
- Bypass rate limits for news requests
- No admin command access

**Setup Steps:**

1. Get your LINE user ID from server logs (appears when you send a message)
2. Add to `.env`:
   - Admins: `ADMIN_USER_IDS=U1234567890abcdef`
   - Moderators: `MODERATOR_USER_IDS=U9876543210fedcba,U1111222233334444`
   - Optional named recipients (admin push): `USER_BOSS=Uaaaaaaaaaaaaaaaa`
3. Restart bot

**See [Admin Commands Guide](docs/ADMIN_COMMANDS.md) for complete documentation.**

## 🏗️ Architecture

Ms. Green uses a **modular multi-agent architecture** where messages are
routed to specialized agents based on content and context.

```text
LINE Webhook → Agent Router → [TranslationAgent | MathAgent | CodeAgent | ...]
```

**Want to understand how it all works?**
See **[Architecture Guide](docs/architecture/overview.md)** and
**[Agents Guide](docs/architecture/agents.md)** for:

- Complete data flow diagrams
- Webhook explanation
- Agent routing system
- How to build custom agents

**Project Structure:**

```text
src/
├── agents/              # Multi-agent system (NEW!)
│   ├── base_agent.py    # Base agent class
│   ├── agent_router.py  # Message routing
│   └── translation_agent.py  # Translation logic
├── handlers/            # Event handlers (join, leave, members)
├── services/            # Translation & session management
│   ├── ai_translation_service.py  # Shared AI translation
│   └── session_manager.py         # Session state
├── config.py           # Environment configuration
└── main.py             # FastAPI entry point
```

## 🤖 Adding Custom Agents

Building new agents is simple! See **[Agents Guide](docs/architecture/agents.md)** for the pattern and priority rules.

```python
from src.agents.base_agent import BaseAgent

class MathAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="MathAgent",
            description="Solves math equations"
        )

    async def should_handle(self, event, text):
        return "solve" in text or re.match(r'\d+\s*[\+\-\*/]', text)

    async def handle(self, event, text, line_bot_api):
        result = solve_equation(text)
        # Send reply...
        return True

# Register in src/main.py
agent_router.register_agent(MathAgent())
```

**Potential Agents:**

- 📐 MathAgent - Equation solver
- 💻 CodeReviewAgent - Code analysis
- 📝 QuizAgent - Vocabulary practice
- 🎨 ArtAgent - Image generation
- 📊 DataAgent - Data visualization

## 🧪 Testing

```bash
# Run tests
pytest

# With coverage
pytest --cov=src --cov-report=html

# Current coverage: 87%
```

## 📊 What's Built

✅ **Multi-Agent System:**

- Modular agent architecture with base class
- Smart message routing by priority
- Translation Agent with session management
- Admin Agent for in-chat bot management **NEW!**
- Easy to extend with new agents

✅ **Translation Features:**

- Smart Thai character detection
- Continuous translation mode
- Shared AI translation via GitHub Models with OpenRouter fallback
- Session management per chat
- "Thanks Ms Green!" sleep command (24h)
- "Dear Ms. Green" wake command
- Rate limiting (10 translations/minute)

✅ **Group Chat Support:**

- Welcome message when bot joins group
- Member join/leave notifications
- Bot leave event handling
- Independent sessions per chat

✅ **Production Ready:**

- Docker containerization
- Environment-based configuration
- Comprehensive error handling
- Health check endpoint
- Async/await throughout

## 🚀 Deployment Options

- **ngrok** - Quick testing (temporary URL)
- **Heroku** - Easy production (free tier)
- **VPS** - Full control (DigitalOcean, AWS, etc.)
- **Render.com** - Simple alternative to Heroku

See **[Deployment Guide](docs/guides/deployment.md)** for complete instructions for each option.

## 📄 License

MIT
