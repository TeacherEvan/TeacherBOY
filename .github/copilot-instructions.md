# GitHub Copilot Instructions for TeacherBOY

## Project Overview

TeacherBOY is a **multi-agent LINE bot** with the following capabilities:
- **Thai/English Translation**: Auto-detects and translates between Thai and English
- **Google Calendar Reminders**: Scheduled reminders at 07:00 (daily) and 14:00 (weekly)

The bot uses a modular agent-based architecture where each agent handles specific triggers and tasks.

## Tech Stack

- **Python 3.11**: Primary programming language
- **FastAPI**: Web framework for handling webhooks
- **LINE Bot SDK v3**: Integration with LINE Messaging API
- **Google Cloud Translation API**: Primary translation service
- **LibreTranslate API**: Fallback translation service
- **Google Calendar API**: Calendar event fetching
- **APScheduler**: Background task scheduling
- **langdetect**: Language detection library
- **Docker**: Containerization
- **MCP**: line-bot-mcp-server for Docker integration

## Project Structure

```
TeacherBOY/
├── src/
│   ├── __init__.py
│   ├── main.py              # FastAPI app, webhook handling, scheduler setup
│   ├── config.py            # Configuration and settings
│   ├── agents/              # Multi-agent system
│   │   ├── __init__.py
│   │   ├── base_agent.py       # Abstract base class for agents
│   │   ├── agent_router.py     # Routes messages to appropriate agent
│   │   ├── translation_agent.py # Handles Thai/English translation
│   │   └── calendar_agent.py    # Google Calendar reminders
│   ├── handlers/
│   │   ├── __init__.py
│   │   └── message_handler.py  # LINE event handlers (join, leave, etc.)
│   └── services/
│       ├── __init__.py
│       ├── translation_service.py  # LibreTranslate integration
│       ├── google_translation.py   # Google Cloud Translation
│       ├── scheduler_service.py    # APScheduler for timed events
│       └── session_manager.py      # Translation session management
├── tests/
│   ├── __init__.py
│   ├── test_translation_service.py
│   └── test_message_handler.py
├── mcp/
│   └── config.json          # MCP server configuration
├── docs/
│   └── LINE_SETUP.md        # LINE Bot setup documentation
├── .github/
│   ├── workflows/
│   │   └── ci.yml           # CI/CD pipeline
│   └── copilot-instructions.md  # This file
├── credentials.json         # Google Calendar OAuth credentials (not committed)
├── token.json               # Google Calendar token (not committed)
├── .env.example             # Environment variables template
├── requirements.txt         # Python dependencies
├── Dockerfile              # Docker image definition
└── docker-compose.yml      # Docker Compose configuration
```

## Key Components

### 1. Agent System (`src/agents/`)

#### BaseAgent (`base_agent.py`)
- Abstract base class for all agents
- Methods: `should_handle()`, `handle()`, `get_priority()`
- Enable/disable functionality

#### AgentRouter (`agent_router.py`)
- Routes incoming messages to appropriate agent
- Priority-based selection (lower number = higher priority)
- Handles agent registration and listing

#### TranslationAgent (`translation_agent.py`) - Priority: 10
- Triggers: Thai text detected OR active session
- Features: Session management, exit command ("thanks Brown")
- Uses Google Translate (primary) or LibreTranslate (fallback)

#### CalendarAgent (`calendar_agent.py`) - Priority: 20
- Triggers: Scheduled at 07:00 and 14:00 (not user messages)
- Features: Daily reminders, weekly overview
- Uses Google Calendar API with OAuth2

### 2. Main Application (`src/main.py`)
- FastAPI application with webhook endpoint
- LINE Bot API initialization
- Agent registration and scheduler setup
- Health check and test endpoints

### 3. Services (`src/services/`)
- **translation_service.py**: LibreTranslate API integration
- **google_translation.py**: Google Cloud Translation API
- **scheduler_service.py**: APScheduler for timed tasks
- **session_manager.py**: Translation session state

## Coding Standards

### Python Style
- Follow PEP 8 style guidelines
- Use type hints for function parameters and return values
- Use async/await for I/O operations
- Add docstrings to all functions and classes
- Keep functions small and focused

### Error Handling
- Always log errors with appropriate level
- Provide user-friendly error messages
- Never expose sensitive information in errors
- Use try-except blocks for external API calls

### Testing
- Write unit tests for all services
- Use pytest for test framework
- Mock external API calls
- Aim for high test coverage

### Environment Variables
- Never commit `.env` file
- Update `.env.example` for new variables
- Use pydantic-settings for configuration
- Validate all required settings on startup

## Development Workflow

### Local Development
```bash
# Set up virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install dependencies
pip install -r requirements.txt

# Run locally
python -m src.main
```

### Docker Development
```bash
# Build and run with Docker Compose
docker-compose up --build

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

### Testing
```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test
pytest tests/test_translation_service.py
```

### Code Quality
```bash
# Format code
black src/ tests/

# Lint code
flake8 src/ tests/

# Type checking
mypy src/
```

## LINE Bot Integration

### Webhook Flow
1. User sends message to LINE bot
2. LINE sends POST request to `/webhook`
3. Signature verification
4. Message event handled
5. Text extracted and sent to translation service
6. Translation returned to user

### Message Format
- Detection indicator: 🌐 Detected: [Language]
- Translation label: 📝 [Target Language] Translation:
- Clear separation between labels and content

## Translation Logic

### Language Detection
- Uses langdetect library
- Supports Thai (`th`) and English (`en`)
- Falls back to English for undetected languages

### Translation Rules
- Thai → English
- English → Thai
- All other languages → Thai (default)

## Security Considerations

### API Keys
- Store in environment variables only
- Never log sensitive tokens
- Use `.env.example` as template

### Webhook Security
- Validate LINE signature on all webhook requests
- Return 400 for invalid signatures
- Log security events

### Data Privacy
- Don't store user messages
- Don't log personal information
- Process messages in memory only

## MCP Integration

The project uses line-bot-mcp-server for Docker MCP integration:
- Configuration in `mcp/config.json`
- Environment variables passed through Docker
- Network mode: host for local development

## Common Tasks

### Adding a New Feature
1. Update relevant service or handler
2. Add tests for new functionality
3. Update documentation
4. Test locally and with Docker
5. Submit PR with description

### Updating Dependencies
1. Update `requirements.txt`
2. Rebuild Docker image
3. Run full test suite
4. Update documentation if needed

### Debugging Issues
1. Check application logs
2. Verify environment variables
3. Test webhook connectivity
4. Check LINE Developer Console
5. Review LibreTranslate API status

## CI/CD Pipeline

The GitHub Actions workflow:
- Runs on push and pull requests
- Executes linting (flake8, black)
- Runs test suite with coverage
- Builds Docker image
- Reports test results

## Useful Commands

```bash
# Quick format and lint
black src/ tests/ && flake8 src/ tests/

# Run tests with verbose output
pytest -v

# Check type hints
mypy src/ --strict

# Build Docker image
docker build -t teacherboy:latest .

# Test webhook locally with ngrok
ngrok http 8000
```

## Resources

- [LINE Messaging API Docs](https://developers.line.biz/en/docs/messaging-api/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [LibreTranslate API](https://libretranslate.com/docs/)
- [Python asyncio Guide](https://docs.python.org/3/library/asyncio.html)

## Contact

- Project Owner: ewaldt91
- Repository: https://github.com/TeacherEvan/TeacherBOY
