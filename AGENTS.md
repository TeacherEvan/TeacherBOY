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
1. ModModeAgent (4) - group moderation: activate mod mode, /modmode commands (intercepts first in mod-enabled groups)
2. HelpAgent (5) - /help commands
3. AdminAgent (5) - admin commands, requires ADMIN_USER_IDS
4. CalendarAgent (6) - calendar/reminder CRUD
5. HannibalProfileAgent (6) - psychological profiling from history
6. ProfilerAgent (7) - image-based psychological profiling
7. ImageAnalyzerAgent (7) - general image Q&A
8. DocumentMemoryAgent (8) - PDF/DOCX storage and retrieval
9. SearchAgent (8) - Brave web search
10. LLMAgent (9) - general chat via LLM fallback chain (Gemini first)
11. TranslationAgent (10) - English↔Thai translation
12. SpecialNewsAgent (12) - Thailand-specific news
13. NewsAgent (15) - general news + weather

## Key Constraints
- **NEVER use Maton AI API key** in this project (Hermes agent uses it separately)
- **LLM fallback chain:** gemini first; OpenRouter/Hermes/HF Inference/Nous/Ollama are fallbacks only if Gemini is unavailable (configurable)
- All LLM providers use OpenAI-compatible API format
- Pydantic Settings for config (env vars)
- HuggingFace Hub used for persistent storage (conversations, calendar, documents, logs)

## Directory Structure
```
src/
├── agents/          # Agent implementations (base_agent.py → specific agents)
│   └── mod_mode/    # ModModeAgent + dashboard (Flex UI)
├── config.py        # Pydantic Settings (all env vars)
├── handlers/        # LINE event handlers
├── main.py          # FastAPI app + lifespan
├── prompts/         # System prompts and frameworks
│   ├── builders/    # Debrief, text, vision prompt builders
│   └── frameworks/  # FBI BAU, Ekman FACS, Navarro, etc.
├── services/        # Business logic services
│   ├── mod_mode_service.py       # ModModeState CRUD (Convex)
│   ├── ban_list_service.py       # BanList CRUD + auto-kick (Convex)
│   ├── warning_service.py        # 3-strike warnings + read tracking + reset_warnings (Convex)
│   ├── harmful_content_detector.py # Configurable keyword + LLM detection (JSON/env)
│   ├── mod_audit_log.py          # HF Hub append-only audit logs
│   ├── metrics_service.py        # In-memory metrics + provider latency
│   ├── ai_translation_service.py # Shared AI translation + latency metrics
│   ├── news/        # News data service
│   └── profiler/    # Profiler framework loader
└── utils/           # Utilities (tracing, text preprocessing, LLM fallback)
tests/               # pytest test suite (70+ test files)
convex/              # Convex backend (TypeScript) for mod mode
    ├── modModeState.ts    # Moderator mode state per group
    ├── banList.ts         # Ban list per group
    └── userWarnings.ts    # 3-strike warnings per group (resetWarnings mutation)
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
- `openrouter_service` - Optional fallback LLM provider (used only if Gemini is unavailable)
- `conversation_memory_service` - chat context persistence
- `calendar_service` - event management + HF sync
- `debrief_extraction_service` - structured lesson debriefs
- `mod_mode_service` - Moderator mode state (Convex)
- `ban_list_service` - Ban list + auto-kick (Convex)
- `warning_service` - 3-strike warnings + reset_warnings (Convex)
- `harmful_content_detector` - Configurable keyword + LLM detection
- `mod_audit_log` - HF Hub audit trail
- `metrics_service` - In-memory metrics + provider latency tracking
- `ai_translation_service` - Shared AI translation with latency metrics
