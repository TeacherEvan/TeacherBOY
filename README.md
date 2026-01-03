---
title: Zeus
emoji: 👨‍🏫
colorFrom: blue
colorTo: green
sdk: docker
app_port: 8000
---

## Zeus 👨‍🏫

**SMOOTH automatic Thai - English translator with Multi-Agent Architecture for LINE.**

Zeus is a high-performance, asynchronous LINE Bot featuring a modular multi-agent system. The Translation Agent provides intelligent Thai/English translation with smart session management. Easily extensible with additional specialized agents.

## 📚 Documentation

**[📖 Complete Documentation Index](DOCUMENTATION_INDEX.md)** - Browse all documentation files organized by category

### Quick Links

- **[📚 Docs Home](docs/README.md)** - Start here (quickstart, deployment, LINE setup, admin)
- **[⚡ Quick Start](docs/guides/quickstart.md)**
- **[⚙️ LINE Setup](docs/guides/line-setup.md)**
- **[🚀 Deployment](docs/guides/deployment.md)**
- **[🏗️ Architecture](docs/architecture/overview.md)**
- **[🤖 Agents](docs/architecture/agents.md)**
- **[🔧 Admin Commands](docs/ADMIN_COMMANDS.md)**
- **[🔎 Tracing](docs/TRACING.md)**

Legacy docs at repo root are kept for backward compatibility.

## 🚀 Features

### Translation Agent (Primary)

- **🔥 Smart Auto-Detection:** Automatically starts when Thai text is detected
- **🔄 Continuous Mode:** Translates EVERY message until you say "amen"
- **😴 Sleep Mode:** Bot sleeps for 24 hours - say "Dear Zeus" alone to wake up
- **🌐 Professional Quality:** Google Translate (primary) + LibreTranslate (fallback)
- **🛡️ Hallucination Prevention:** Detects incomplete sentences and prevents unwanted context injection
- **💬 Bi-directional:** Thai 🇹🇭 → English 🇬🇧 and English 🇬🇧 → Thai 🇹🇭
- **👥 Group Chat Support:** Works in 1-on-1, groups, and multi-person chats
- **📝 Text-Only Responses:** Clean, simple text translations (no distracting cards)
- **🤫 Silent Join:** Bot joins groups silently - only speaks when Thai is detected
- **👋 Welcome Message:** Sends "Welcome friend / ยินดีต้อนรับเพื่อน" when added as friend
- **🎯 Session Management:** Independent sessions per chat
- **📋 Parentheses Preservation:** Names and notes in (parentheses) are never translated
- **⏱️ Rate Limiting:** 10 requests per minute (admins unlimited)

### News Agent **NEW!**

- **📰 Real-time News:** Bangkok weather, air quality, PM2.5, and Thai news headlines
- **🌡️ Weather Data:** Temperature and 5-hour rain forecast via Open-Meteo (no API key for non-commercial use; subject to Open-Meteo terms)
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

### Zeus AI (LLM Agent) **NEW!**

- **🤖 Ask Zeus:** `Zeus <question>` or `/zeus <question>`
- **🌡️ Warmth (Temperature):** Configure via `LLM_TEMPERATURE` (default: `1.0`)
- **🧊 Stoic Persona (Default):** Controlled by `LLM_SYSTEM_PROMPT` (optional override)
- **👥 Group Access Policy:**
  - Admins can use Zeus anywhere
  - Non-admins follow `ZEUS_GROUP_ACCESS_MODE`:
    - `all` (default)
    - `allowlist` with `ZEUS_ALLOWED_GROUP_IDS`
    - `denylist` with `ZEUS_DENIED_GROUP_IDS`
- **🧑‍💼 Boss Easter Egg:** If asked “who is boss”, replies with exactly: `Evan...`

### Psychological Profiler **NEW!**

- **🔬 FBI/Ekman/Navarro Frameworks:** Professional behavioral analysis
- **📸 Trigger-Based:** Send "zeus profile" then your image
- **🎨 Fictional Artwork Support:** Analyze anime, manga, pencil drawings, concept art
- **♿ Accessibility:** Helps neurodivergent users (autism) understand character expressions
- **🎬 Creative Projects:** Art direction for music videos, storytelling, visual narratives
- **⏱️ Rate Limiting:** 3 analyses/hour (admins unlimited)
- **🤖 Vision AI:** GPT-4o multimodal analysis
- **Full Documentation:** [Profiler Usage Guide](docs/PROFILER_USAGE.md)

### Image Analyzer **NEW!**

- **🖼️ General Image Q&A:** Ask Zeus questions about any image
- **🔄 Multi-Step Flow:**
  1. Trigger: "Zeus analyze this" / "analyze image" / "examine this"
  2. Zeus asks for the image (60 seconds timeout)
  3. Send your image
  4. Zeus asks what you want to know
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
- **💭 Conversation Memory:** Multi-turn context for Zeus LLM agent with optional HF Hub persistence **NEW!**
- **📜 History Logging:** Comprehensive audit trail with encryption and cloud backup **NEW!**

### Performance & Scalability

- **High Performance:** Built on **FastAPI** with full async support
- **Connection Pooling:** Efficient HTTP client management
- **Docker-Ready:** Easy deployment and scaling
- **Stateless:** Horizontal scaling support

## 🛠️ Tech Stack

- **Framework:** Python 3.11+, FastAPI
- **Platform:** LINE Messaging API v3 (Async)
- **Translation:** Google Cloud Translation API (primary), LibreTranslate (fallback)
- **Architecture:** Multi-agent system with modular design
- **Libraries:** `line-bot-sdk`, `httpx`, `pydantic`

## ⚙️ Quick Start

### 1. Get LINE Tokens

See **[LINE Setup Guide](docs/guides/line-setup.md)** for detailed instructions.

**Already have tokens?** Create a `.env` file:

```env
# Primary Agent - Zeus (Translation)
LINE_CHANNEL_SECRET=your_channel_secret
LINE_CHANNEL_ACCESS_TOKEN=your_channel_access_token

# Translation APIs
GOOGLE_TRANSLATE_API_KEY=your_google_api_key  # Recommended!
LIBRETRANSLATE_API_URL=https://libretranslate.de/translate

# News Agent (optional)
# NEWS_API_KEY is deprecated (headlines use RSS feeds; no key required)
# NEWS_API_KEY=

# Optional: Additional agents
ADDITIONAL_AGENTS=

# Zeus AI (LLM) (optional)
LLM_TEMPERATURE=1.0
# Group/room policy for non-admin Zeus usage: all|allowlist|denylist
ZEUS_GROUP_ACCESS_MODE=all
ZEUS_ALLOWED_GROUP_IDS=
ZEUS_DENIED_GROUP_IDS=
# Optional: override Zeus persona
# LLM_SYSTEM_PROMPT=

# Admin Control (for bot management)
ADMIN_USER_IDS=

# Optional: named recipients for admin push messaging
# Format: USER_<ALIAS>=<LINE_USER_ID>
USER_BOSS=

DEBUG=False
```

### 2. Run Locally

```bash
# With Docker (recommended)
docker build -t zeus .
docker run --env-file .env -p 8000:8000 zeus

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
- Say: `amen` → Bot sleeps for 24 hours 😴
- Say: `Dear Zeus` → Bot wakes up! ☀️

**The bot will translate EVERY message until you say "amen"!**

**Need help?** See **[Quick Start Guide](docs/guides/quickstart.md)** or **[Deployment Guide](docs/guides/deployment.md)**.

### 6. Admin & Moderator Setup (Optional)

For bot management and privileged access, Zeus supports two levels:

**Admin Users (Full Control):**

- `/admin` commands for bot management (status, sleep, wake, reset, etc.)
- Unlimited API access (bypass rate limits)
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

Zeus uses a **modular multi-agent architecture** where messages are routed to specialized agents based on content and context.

```text
LINE Webhook → Agent Router → [TranslationAgent | MathAgent | CodeAgent | ...]
```

**Want to understand how it all works?** See **[Architecture Guide](docs/architecture/overview.md)** and **[Agents Guide](docs/architecture/agents.md)** for:

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
│   ├── translation_service.py     # LibreTranslate
│   ├── google_translation.py      # Google API
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
- Google Translate + LibreTranslate fallback
- Session management per chat
- "amen" sleep command (24h)
- "Dear Zeus" wake command
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
