# TeacherBOY 👨‍🏫

**SMOOTH automatic Thai - English translator for LINE.**

TeacherBOY is a high-performance, asynchronous LINE Bot that automatically translates messages between Thai and English using LibreTranslate.

## 📚 Documentation

- **[🏗️ Architecture & How It Works](ARCHITECTURE.md)** - Complete explanation of how the bot works, data flow, and webhook concepts
- **[🚀 Deployment Guide](DEPLOYMENT_GUIDE.md)** - Step-by-step deployment with ngrok, Heroku, VPS, or Render
- **[⚙️ LINE Setup Guide](docs/LINE_SETUP.md)** - Getting your LINE tokens and configuring webhooks
- **[📋 Implementation Summary](IMPLEMENTATION_SUMMARY.md)** - Technical details and test results

## 🚀 Features

- **Automatic Language Detection:** Instantly detects if the message is Thai or English.
- **Bi-directional Translation:** Translates Thai 🇹🇭 → English 🇬🇧 and English 🇬🇧 → Thai 🇹🇭.
- **Premium UX:** Returns translations in beautiful **Flex Messages** with clear language indicators.
- **Group Chat Support:** Works in 1-on-1 chats and group conversations.
- **High Performance:** Built on **FastAPI** with full async support and connection pooling.
- **Scalable:** Docker-ready and stateless architecture.

## 🛠️ Tech Stack

- **Framework:** Python 3.11+, FastAPI
- **Platform:** LINE Messaging API (Async)
- **Translation:** LibreTranslate (Self-hosted or API)
- **Libraries:** `line-bot-sdk`, `httpx`, `langdetect`, `pydantic`

## ⚙️ Quick Start

### 1. Get LINE Tokens

See **[LINE Setup Guide](docs/LINE_SETUP.md)** for detailed instructions.

**Already have tokens?** Create a `.env` file:

```env
LINE_CHANNEL_SECRET=your_channel_secret
LINE_CHANNEL_ACCESS_TOKEN=your_channel_access_token
LIBRETRANSLATE_API_URL=https://libretranslate.de/translate
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
- Send: `สวัสดี` → Get English translation
- Send: `Hello` → Get Thai translation

**Need help?** See **[Deployment Guide](DEPLOYMENT_GUIDE.md)** for detailed instructions.

## 🏗️ Architecture

TeacherBOY receives webhooks from LINE, detects the language, translates via LibreTranslate, and replies with beautiful Flex Message cards.

**Want to understand how it all works?** See **[Architecture Guide](ARCHITECTURE.md)** for:

- Complete data flow diagrams
- Webhook explanation
- Security features
- Component breakdown

**Project Structure:**

- **`src/main.py`**: FastAPI entry point with async webhook handling
- **`src/handlers/`**: Message processing and event handlers (text, join, leave, members)
- **`src/services/`**: Translation service with language detection
- **`src/utils/`**: Flex Message templates and utilities
- **`src/config.py`**: Environment configuration with Pydantic

## 🧪 Testing

```bash
# Run tests
pytest

# With coverage
pytest --cov=src --cov-report=html

# Current coverage: 87%
```

## 📊 What's Built

✅ **Core Features:**

- Automatic Thai/English language detection
- Bidirectional translation (Thai ↔ English)
- Beautiful Flex Message cards with flags
- FastAPI async webhook handler
- LINE signature validation

✅ **Group Chat Support:**

- Welcome message when bot joins group
- Member join/leave notifications
- Bot leave event handling

✅ **Production Ready:**

- Docker containerization
- Environment-based configuration
- Comprehensive error handling
- Health check endpoint
- 87% test coverage

## 🚀 Deployment Options

- **ngrok** - Quick testing (temporary URL)
- **Heroku** - Easy production (free tier)
- **VPS** - Full control (DigitalOcean, AWS, etc.)
- **Render.com** - Simple alternative to Heroku

See **[Deployment Guide](DEPLOYMENT_GUIDE.md)** for complete instructions for each option.

## �� License

MIT
