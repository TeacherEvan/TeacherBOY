# TeacherBOY 👨‍🏫

**SMOOTH automatic Thai - English translator with Multi-Agent Architecture for LINE.**

TeacherBOY is a high-performance, asynchronous LINE Bot featuring a modular multi-agent system. The Translation Agent provides intelligent Thai/English translation with smart session management. Easily extensible with additional specialized agents.

## 📚 Documentation

- **[🏗️ Architecture & How It Works](ARCHITECTURE.md)** - Complete explanation of how the bot works, data flow, and webhook concepts
- **[🚀 Deployment Guide](DEPLOYMENT_GUIDE.md)** - Step-by-step deployment with ngrok, Heroku, VPS, or Render
- **[🤖 Multi-Agent Guide](MULTI_AGENT_GUIDE.md)** - **NEW!** Build custom agents for math, code review, quizzes, and more
- **[⚡ Quick Start](QUICK_START.md)** - Fast setup with Google Translate API integration
- **[⚙️ LINE Setup Guide](docs/LINE_SETUP.md)** - Getting your LINE tokens and configuring webhooks
- **[📋 Implementation Summary](IMPLEMENTATION_SUMMARY.md)** - Technical details and test results

## 🚀 Features

### Translation Agent (Primary)

- **🔥 Smart Auto-Detection:** Automatically starts when Thai text is detected
- **🔄 Continuous Mode:** Translates EVERY message until you say "Thank you TeacherBoy"
- **😴 Sleep Mode:** Bot sleeps for 24 hours - say "TeacherBoy" alone to wake up
- **🌐 Professional Quality:** Google Translate (primary) + LibreTranslate (fallback)
- **💬 Bi-directional:** Thai 🇹🇭 → English 🇬🇧 and English 🇬🇧 → Thai 🇹🇭
- **👥 Group Chat Support:** Works in 1-on-1, groups, and multi-person chats
- **📱 Beautiful UI:** Flex Message cards with original and translated text
- **🎯 Session Management:** Independent sessions per chat

### Multi-Agent Architecture **NEW!**

- **🏗️ Modular Design:** Easy to add agents with different capabilities
- **⚡ Smart Routing:** Messages routed to appropriate agent by priority
- **🔌 Extensible:** Add math solver, code review, quiz agents, and more!
- **🎨 Clean API:** Simple `BaseAgent` class to inherit from
- **📊 Priority System:** Control which agent handles messages first

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

See **[LINE Setup Guide](docs/LINE_SETUP.md)** for detailed instructions.

**Already have tokens?** Create a `.env` file:

```env
# Primary Agent - TeacherBOY (Translation)
LINE_CHANNEL_SECRET=your_channel_secret
LINE_CHANNEL_ACCESS_TOKEN=your_channel_access_token

# Translation APIs
GOOGLE_TRANSLATE_API_KEY=your_google_api_key  # Recommended!
LIBRETRANSLATE_API_URL=https://libretranslate.de/translate

# Optional: Additional agents
ADDITIONAL_AGENTS=

DEBUG=False
```

### 2. Run Locally

```bash
# With Docker (recommended)
docker build -t teacherboy .
docker run --env-file .env -p 8000:8000 teacherboy

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

### 5. Test!

- Scan QR code to add bot
- Send: `สวัสดีครับ` → Translation mode starts! 🔥
- Send: `Hello` → Translates to Thai automatically
- Send: `How are you?` → Keeps translating
- Say: `Thank you TeacherBoy` → Bot sleeps for 24 hours 😴
- Say: `TeacherBoy` → Bot wakes up! ☀️

**The bot will translate EVERY message until you say "Thank you TeacherBoy"!**

**Need help?** See **[Quick Start Guide](QUICK_START.md)** or **[Deployment Guide](DEPLOYMENT_GUIDE.md)** for detailed instructions.

## 🏗️ Architecture

TeacherBOY uses a **modular multi-agent architecture** where messages are routed to specialized agents based on content and context.

```
LINE Webhook → Agent Router → [TranslationAgent | MathAgent | CodeAgent | ...]
```

**Want to understand how it all works?** See **[Architecture Guide](ARCHITECTURE.md)** and **[Multi-Agent Guide](MULTI_AGENT_GUIDE.md)** for:

- Complete data flow diagrams
- Webhook explanation
- Agent routing system
- How to build custom agents

**Project Structure:**

```
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

Building new agents is simple! See **[Multi-Agent Guide](MULTI_AGENT_GUIDE.md)** for complete tutorial.

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
- Easy to extend with new agents

✅ **Translation Features:**

- Smart Thai character detection
- Continuous translation mode
- Google Translate + LibreTranslate fallback
- Session management per chat
- "Thank you TeacherBoy" sleep command (24h)
- "TeacherBoy" wake command
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

See **[Deployment Guide](DEPLOYMENT_GUIDE.md)** for complete instructions for each option.

## �� License

MIT
