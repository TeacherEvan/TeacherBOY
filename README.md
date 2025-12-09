# TeacherBOY 👨‍🏫

**SMOOTH automatic Thai - English translator for LINE.**

TeacherBOY is a high-performance, asynchronous LINE Bot that automatically translates messages between Thai and English using LibreTranslate.

## 🚀 Features

- **Automatic Language Detection:** Instantly detects if the message is Thai or English.
- **Bi-directional Translation:** Translates Thai 🇹🇭 → English 🇬🇧 and English 🇬🇧 → Thai 🇹🇭.
- **Premium UX:** Returns translations in beautiful **Flex Messages** with clear language indicators.
- **High Performance:** Built on **FastAPI** with full async support and connection pooling.
- **Scalable:** Docker-ready and stateless architecture.

## 🛠️ Tech Stack

- **Framework:** Python 3.11+, FastAPI
- **Platform:** LINE Messaging API (Async)
- **Translation:** LibreTranslate (Self-hosted or API)
- **Libraries:** `line-bot-sdk`, `httpx`, `langdetect`, `pydantic`

## ⚙️ Configuration

Create a `.env` file in the root directory:

```env
LINE_CHANNEL_SECRET=your_channel_secret
LINE_CHANNEL_ACCESS_TOKEN=your_channel_access_token
LIBRETRANSLATE_API_URL=https://libretranslate.de/translate
# LIBRETRANSLATE_API_KEY=optional_api_key
DEBUG=False
```

## 🏃‍♂️ Running the Bot

### Local Development

```bash
pip install -r requirements.txt
uvicorn src.main:app --reload
```

### Docker

```bash
docker-compose up --build
```

## 🏗️ Architecture

- **`src/main.py`**: FastAPI entry point with async webhook handling.
- **`src/handlers`**: Business logic for message processing.
- **`src/services`**: External service integrations (Translation).
- **`src/utils`**: Helper functions and Flex Message templates.

## �� License

MIT
