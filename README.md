# TeacherBOY 🤖

**SMOOTH automatic Thai - English translator for LINE**

TeacherBOY is an intelligent LINE bot that automatically detects and translates messages between Thai and English. Perfect for language learners, travelers, and anyone communicating across Thai and English languages.

[![CI/CD Pipeline](https://github.com/TeacherEvan/TeacherBOY/actions/workflows/ci.yml/badge.svg)](https://github.com/TeacherEvan/TeacherBOY/actions/workflows/ci.yml)

## ✨ Features

- 🔄 **Automatic Language Detection**: Instantly detects Thai or English text
- 🌐 **Bidirectional Translation**: Thai ↔ English translation
- ⚡ **Real-time Response**: Fast translation powered by LibreTranslate API
- 🐳 **Docker Ready**: Easy deployment with Docker and Docker Compose
- 🔧 **MCP Integration**: Supports line-bot-mcp-server for Docker MCP
- 📱 **LINE Integration**: Seamless integration with LINE Messaging API

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- Docker and Docker Compose (optional, but recommended)
- LINE Developer account
- LINE Bot channel (see [LINE Setup Guide](docs/LINE_SETUP.md))

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/TeacherEvan/TeacherBOY.git
   cd TeacherBOY
   ```

2. **Set up environment variables**
   ```bash
   cp .env.example .env
   # Edit .env and add your LINE Bot tokens
   ```

3. **Choose your deployment method**

#### Option A: Docker Compose (Recommended)
```bash
docker-compose up -d
```

#### Option B: Docker
```bash
docker build -t teacherboy .
docker run -p 8000:8000 --env-file .env teacherboy
```

#### Option C: Local Development
```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the application
python -m src.main
```

## 📖 Documentation

- **[LINE Bot Setup Guide](docs/LINE_SETUP.md)** - Complete guide to setting up your LINE Bot
- **[GitHub Copilot Instructions](.github/copilot-instructions.md)** - Developer guidelines and best practices

## 🏗️ Project Structure

```
TeacherBOY/
├── src/
│   ├── main.py                 # FastAPI application
│   ├── config.py               # Configuration management
│   ├── handlers/               # LINE message handlers
│   │   └── message_handler.py
│   └── services/               # Business logic
│       └── translation_service.py
├── tests/                      # Test suite
│   ├── test_main.py
│   ├── test_message_handler.py
│   └── test_translation_service.py
├── mcp/
│   └── config.json            # MCP server configuration
├── docs/
│   └── LINE_SETUP.md          # Setup documentation
├── .github/
│   └── workflows/
│       └── ci.yml             # CI/CD pipeline
├── requirements.txt           # Python dependencies
├── Dockerfile                 # Docker image definition
├── docker-compose.yml         # Docker Compose configuration
└── .env.example              # Environment variables template
```

## 🧪 Testing

Run the test suite:

```bash
# Run all tests
pytest

# Run with coverage report
pytest --cov=src --cov-report=html

# Run specific test file
pytest tests/test_translation_service.py
```

## 🔧 Development

### Code Quality

```bash
# Format code
black src/ tests/

# Lint code
flake8 src/ tests/

# Type checking
mypy src/
```

### Local Development with ngrok

For local testing with LINE webhooks:

```bash
# Start the application
python -m src.main

# In another terminal, expose via ngrok
ngrok http 8000

# Update webhook URL in LINE Developer Console
# Use the ngrok URL (e.g., https://abc123.ngrok.io/webhook)
```

## 🌐 API Endpoints

- `GET /` - Service information
- `GET /health` - Health check endpoint
- `POST /webhook` - LINE webhook endpoint (for LINE platform use)

## ⚙️ Configuration

Edit `.env` file with your settings:

```env
# LINE Bot Configuration
LINE_CHANNEL_SECRET=your_channel_secret
LINE_CHANNEL_ACCESS_TOKEN=your_access_token

# LibreTranslate API
LIBRETRANSLATE_API_URL=https://libretranslate.de/translate
LIBRETRANSLATE_API_KEY=  # Optional

# Server Configuration
HOST=0.0.0.0
PORT=8000
DEBUG=False
```

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 👤 Author

**ewaldt91**

- GitHub: [@TeacherEvan](https://github.com/TeacherEvan)

## 🙏 Acknowledgments

- [LINE Messaging API](https://developers.line.biz/en/docs/messaging-api/)
- [LibreTranslate](https://libretranslate.com/) - Open-source translation API
- [FastAPI](https://fastapi.tiangolo.com/) - Modern Python web framework
- [langdetect](https://github.com/Mimino666/langdetect) - Language detection library

## 📞 Support

If you have any questions or issues, please:

1. Check the [LINE Setup Guide](docs/LINE_SETUP.md)
2. Search existing [GitHub Issues](https://github.com/TeacherEvan/TeacherBOY/issues)
3. Create a new issue if needed

---

Made with ❤️ for language learners in Thailand
