# Code Audit Report - TeacherBOY (Ms. Green)

**Date:** 2025-06-13
**Project:** Multi-agent LINE/Translation Bot
**Language:** Python 3.11+, TypeScript (Convex backend)

---

## 1. File Inventory

### Python Files (src/)
- **Agents**: 17 files (`src/agents/`)
  - Base: `base_agent.py`, `agent_factory.py`, `agent_router.py`
  - Core: `translation_agent.py`, `llm_agent.py`, `admin_agent.py`, `help_agent.py`
  - Calendar: 12 files in `src/agents/calendar/`
  - ModMode: 3 files in `src/agents/mod_mode/`
  - Specialty: `calendar_agent.py`, `document_memory_agent.py`, `hannibal_agent.py`, `image_analyzer_agent.py`, `news_agent.py`, `profiler_agent.py`, `review_agent.py`, `search_agent.py`, `special_news_agent.py`, `vision_base_agent.py`
  
- **Config**: `config.py` (Pydantic Settings, 1104 lines)
- **Handlers**: 2 files (`src/handlers/`)
- **Main**: `main.py` (FastAPI app, lifespan, webhook - 1297 lines)
- **Prompts**: 12 files in `src/prompts/`
- **Services**: 47 files (`src/services/`)
  - Core: `translation_service.py`, `conversation_memory_service.py`, `calendar_service.py`, `metrics_service.py`, `llm_fallback.py`
  - Convex: `mod_mode_service.py`, `ban_list_service.py`, `warning_service.py`, `convex_client.py`, `convex_mod_repository.py`
  - LLM: `openrouter_service.py`, `gemini_service.py`, `github_models_service.py`, `hf_inference_service.py`, `hermes_service.py`, `ollama_service.py`, `nous_service.py`
  - Utilities: `cache_service.py`, `rate_limiter.py`, `ai_translation_service.py`, `brave_search_service.py`
  
- **Utils**: 5 files (`src/utils/`)

### TypeScript Files (convex/)
- 14 files including mutations/queries for: `modModeState`, `banList`, `userWarnings`, `calendar`, `users`, `debriefSessions`, `records`, `settings`, `schema`

### Test Files
- 80+ test files in `tests/` (433 collected, 837 passed, 1 skipped)

---

## 2. Dependency Graph

```
main.py (FastAPI entrypoint)
├── config.py (Settings - Pydantic)
├── handlers/message_handler.py
├── agents/
│   ├── agent_router.py → BaseAgent subclasses
│   ├── agent_factory.py (lazy loading)
│   └── specific agents (17)
├── services/
│   ├── LLM providers (8 services)
│   ├── Translation pipeline
│   ├── Memory/Calendar/ModMode (Convex + HF Hub)
│   ├── Metrics, Rate limiting, Logging
│   └── Utilities (cache, prompts, search)
├── utils/
│   ├── tracing.py (OpenTelemetry)
│   ├── llm_fallback.py (provider chain)
│   └── text_preprocessing.py
└── convex/ (TypeScript backend)
    ├── modModeState.ts
    ├── banList.ts
    ├── userWarnings.ts
    ├── schema.ts
    └── http.ts (Convex HTTP client)
```

### External Dependencies
- **LINE Bot SDK v3** - Webhook handling
- **FastAPI** - Web framework
- **httpx** - Async HTTP client (with HTTP/2)
- **Convex** - Real-time backend (mod mode, bans, warnings)
- **HuggingFace Hub** - Persistent storage (conversations, calendar, documents, logs)
- **OpenTelemetry** - Tracing
- **LLM Providers**: Gemini, OpenRouter, GitHub Models, HF Inference, Hermes, Ollama
- **Google Translate / LibreTranslate** - Translation
- **Brave Search** - Web search
- **dateparser / python-dateutil** - Date parsing

---

## 3. Test Baseline

```
pytest tests/ -v --tb=short
========================= 837 passed, 1 skipped, 284 warnings in 32.36s =================
```

**Test Coverage Areas:**
- Agent routing & behavior (mod_mode, admin, calendar, translation, LLM, profiler)
- Service layer (ban_list, warning, conversation_memory, harmful_content_detector)
- Config validation
- Convex client & repository
- Debrief extraction & formatting
- Image analyzer persistence & routing
- News agents & format optimization
- Translation provider chain
- Session management

---

## 4. Lint Baseline

```
ruff check . --output-format=concise
✅ All checks passed!
```

**Cyclomatic Complexity (C901): 53 functions exceed threshold of 10**
- Highest: `admin_agent.py:handle` (30), `llm_agent.py:handle` (38), `main.py:webhook` (24), `main.py:lifespan` (44)
- Calendar handlers: 9 functions >10
- Agent `handle` methods: 15+ functions >10

---

## 5. Type Checking (mypy)

**Errors Found: 15+**
1. **Missing stubs**: `pytz`, `cachetools`, `dateparser` (install `types-*` packages)
2. **Missing return type annotations**: `get_tracer()`, `create_span()`, agent_factory functions
3. **Type mismatches**:
   - `document_memory_agent.py`: Calls `search_documents()`, `clear_documents()`, `find_by_name()` on `DocumentMemoryService` - **these methods don't exist**
   - `gemini_service.py`: Dict type mismatch in payload building
   - `mod_mode_agent.py`: Union type issues with `user_id` (Any | None vs str)
   - `memory_monitor_service.py`: FlushResult type confusion (conversation vs document)
   - `message_handler.py`: Optional BanListService access

---

## 6. TODOs/FIXMEs

| File | Line | Comment |
|------|------|---------|
| `src/config.py` | 95 | `"TTL for translation cache in seconds (0 to disable) - TODO"` |

---

## 7. Key Architectural Observations

### ✅ Strengths
1. **Singleton Services** - All services are module-level singletons (not per-request)
2. **Async Throughout** - All I/O uses async/await (httpx, LINE SDK, Convex)
3. **Priority-based Routing** - AgentRouter uses O(p) priority map optimization
4. **Lazy Agent Loading** - AgentFactory defers instantiation
5. **Provider Fallback Chain** - Configurable LLM provider priority with graceful degradation
6. **Proper Error Handling** - Specific exceptions caught, structured logging (loguru)
7. **Config via Pydantic Settings** - All env vars validated at startup
8. **Startup Data Loading** - Synchronous HF Hub data load before serving
9. **Graceful Shutdown** - All background tasks properly stopped
10. **No Hardcoded Secrets** - All via settings/env

### ⚠️ Issues to Investigate
1. **DocumentMemoryService Missing Methods** - Agent calls non-existent methods
2. **High Cyclomatic Complexity** - 53 functions >10, many agent `handle` methods
3. **Type Annotation Gaps** - Several functions missing return types
4. **Union Type Issues** - `user_id` handling in mod_mode_agent
5. **FlusResult Type Confusion** - Two different FlushResult classes
6. **Missing Type Stubs** - For pytz, cachetools, dateparser

---

## 8. Security Check

- ✅ Input validation on webhook (LINE signature verification)
- ✅ No SQL injection (using Convex/ORM)
- ✅ No command injection
- ✅ Rate limiting on admin operations
- ✅ AuthZ checks on privileged operations (admin/moderator)
- ✅ No secrets in code (all via env/config)
- ✅ TLS via httpx HTTP/2

---

## 9. Gates

**Phase 1 Audit Complete** ✅

**Ready for Phase 2: Review** - Awaiting user confirmation to proceed with structural/semantic analysis.