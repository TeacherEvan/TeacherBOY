# TeacherBOY — Next Phase Enhancements

**Date:** 2026-06-06
**Author:** Hermes (Evan's coding agent)
**Status:** Ready for approval

---

## Context

TeacherBOY (Ms. Green) is a production multi-agent LINE/Telegram bot deployed on
HuggingFace Spaces. Recent work cleaned up codebase: ruff linting (3,690 → 44 errors),
fixed critical bugs, added AGENTS.md, CI improvements.

The goal of this phase is to **harden production quality** and **unlock educational
features** that make the bot more useful for Thai students.

---

## Current State Assessment

### Strengths
- 12 specialized agents with priority routing
- Async throughout (FastAPI + httpx pooling)
- HF Hub persistence for conversations, calendar, documents
- Comprehensive test suite (70+ test files)
- CI pipeline with Trivy security scanning
- Multi-LLM fallback chain (hermes → openrouter → github)

### Weaknesses (from review)
- loguru and instructor added to requirements but never integrated
- No structured logging — errors only in stdout
- Debrief extraction relies on free-form LLM output (fragile)
- admin_agent.py is 1,600+ lines (god object)
- No persistent storage on HF Spaces (data lost on restart)
- No LLM observability (can't trace cost/quality)

---

## Proposed Enhancements (3 approaches)

### Approach A: Observability First (RECOMMENDED)
Focus on understanding what's happening in production before adding features.

**Changes:**
1. Integrate loguru → structured JSON logs with rotation
2. Add Phoenix (Arize) for LLM tracing → see every prompt/response/cost
3. Use instructor for debrief extraction → guaranteed Pydantic schemas
4. Enable HF Spaces persistent storage (50GB free)

**Trade-offs:**
- ✅ Lowest risk — doesn't change bot behavior
- ✅ Makes debugging 10x easier
- ✅ No new features visible to users (internal only)
- ❌ Doesn't add student-facing improvements

**Effort:** ~2 days

---

### Approach B: Educational Features First
Focus on student-facing value.

**Changes:**
1. Implement instructor-based structured debriefs
2. Add quiz generation agent (from lesson history)
3. Add progress tracking per user (Convex + HF storage)
4. Daily learning summaries pushed via LINE

**Trade-offs:**
- ✅ Directly improves student experience
- ✅ Leverages existing debrief_extraction_service
- ❌ Harder to debug if things break (no observability)
- ❌ Requires new Convex schema for progress tracking

**Effort:** ~4 days

---

### Approach C: Architecture Cleanup
Refactor for long-term maintainability.

**Changes:**
1. Split admin_agent.py into sub-modules
2. Add atomic file writes to all services
3. Implement proper error taxonomy
4. Add integration tests for agent routing

**Trade-offs:**
- ✅ Reduces tech debt
- ✅ Makes future features easier to build
- ❌ No user-visible improvements
- ❌ High risk of introducing regressions

**Effort:** ~3 days

---

## Recommendation

**Approach A (Observability First)** — build the foundation, then features.

Rationale:
1. Without logs/tracing, we're flying blind on HF Spaces
2. loguru + instructor are already in requirements.txt — low integration cost
3. Phoenix gives us the data to decide what features to build next
4. Persistent storage prevents data loss on Space restarts

After A is complete, we have the tooling to execute B safely.

---

## Success Criteria

- [ ] Structured JSON logs deployed, visible in HF Spaces logs
- [ ] Phoenix traces showing prompt/response/cost for every LLM call
- [ ] Debrief extraction returns validated Pydantic models (no more JSON parsing errors)
- [ ] HF Spaces persistent storage enabled, conversation data survives restarts
- [ ] Zero regressions in existing tests

---

## Constraints

- Must NOT use Maton AI API key
- Must work within HF Spaces Docker SDK limitations
- Must not break existing LINE webhook handling
- Must keep startup time under 30 seconds (HF Spaces timeout)
