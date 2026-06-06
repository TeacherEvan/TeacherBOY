# TeacherBOY (Ms. Green) - Agent Context

## Overview
Multi-agent LINE/Telegram translation bot deployed on HuggingFace Spaces (Gradio + Docker).
Python 3.11, FastAPI, LINE Bot SDK v3, async/await throughout.

## Architecture
- **FastAPI app** with LINE webhook handler (NOT Telegram native - uses LINE SDK)
- **Agent Router** dispatches messages to priority-ordered agents
- **Services layer** handles LLM calls, translation, calendar, memory, etc.
- **HF Spaces deployment** via Docker SDK with GitHub Actions auto-sync

## Agents (priority order)
1. HelpAgent (5) - /help commands
2. AdminAgent (5) - admin commands, requires ADMIN_USER_IDS
3. CalendarAgent (6) - calendar/reminder CRUD
4. HannibalProfileAgent (6) - psychological profiling from history
5. ProfilerAgent (7) - image-based psychological profiling
6. ImageAnalyzerAgent (7) - general image Q&A
7. SearchAgent (8) - Brave web search
8. LLMAgent (9) - general chat via OpenRouter/GitHub Models/Hermes fallback
9. TranslationAgent (10) - English↔Thai translation
10. SpecialNewsAgent (12) - Thailand-specific news
11. NewsAgent (15) - general news + weather

## Key Constraints
- **NEVER use Maton AI API key** in this project (Hermes agent uses it separately)
- LLM fallback chain: hermes → openrouter → github (configurable)
- All LLM providers use OpenAI-compatible API format
- Pydantic Settings for config (env vars)
- HuggingFace Hub used for persistent storage (conversations, calendar, documents, logs)

## Directory Structure
```
src/
├── agents/          # Agent implementations (base_agent.py → specific agents)
├── config.py        # Pydantic Settings (all env vars)
├── handlers/        # LINE event handlers
├── main.py          # FastAPI app + lifespan
├── prompts/         # System prompts and frameworks
│   ├── builders/    # Debrief, text, vision prompt builders
│   └── frameworks/  # FBI BAU, Ekman FACS, Navarro, etc.
├── services/        # Business logic services
│   ├── news/        # News data service
│   └── profiler/    # Profiler framework loader
└── utils/           # Utilities (tracing, text preprocessing, LLM fallback)
tests/               # pytest test suite (70+ test files)
convex/              # Convex backend (TypeScript) for debrief sessions
```

## Testing
```bash
pytest tests/ -v --tb=short
```
Tests mock external APIs. No real API keys needed for testing.
Environment variables LINE_CHANNEL_SECRET and LINE_CHANNEL_ACCESS_TOKEN must be set (any string works for tests).

## Code Style
- Ruff for linting and formatting (replaces black + flake8)
- Type hints throughout
- Async/await for all I/O
- Pydantic models for data validation
- Services are singletons (module-level instances)

## Deployment
```bash
# Local dev
docker-compose up

# Deploy to HF Spaces (GitHub Actions handles this on push to main)
# Manual: git push hf HEAD:main
```

## Key Services
- `translation_service` - LINE translation pipeline
- `openrouter_service` - LLM via OpenRouter (free models)
- `conversation_memory_service` - chat context persistence
- `calendar_service` - event management + HF sync
- `debrief_extraction_service` - structured lesson debriefs
