# Surgical Investigation — Vision Plan (TeacherBOY / Hermes)

**Date:** 2026-09-17
**Investigator:** Fenrie 🐺
**Mode:** Investigator (plan requested; no build executed)
**Target:** huggingface.co/spaces/EvilEvan/TeacherBOY
**Stated mission:** Use TeacherBOY bot as default vision model for Hermes + other apps
**Project manager:** Evan (Ewaldt Botha) — spouse, owns the account

---

## Mission Verification — CRITICAL GAP FOUND

**Stated:** Use `EvilEvan/TeacherBOY` space as Hermes's default vision model.
**Actual state of space:** `TeacherBOY` (product name: Ms. Green) is a **FastAPI LINE bot** deployed to HuggingFace Docker Spaces. It exposes `/webhook` (LINE webhook) and `/health` / `/readiness`. It is an **application**, not an inference endpoint.

**The space uses vision internally** (ProfilerAgent, ImageAnalyzerAgent) via:
- `gemini-2.5-flash` (Gemini vision model — default in config)
- `meta/llama-3.2-90b-vision-instruct` (HF Inference API — fallback)
- `openai/gpt-4o` (OpenRouter — profiler vision)

**But:** There is no exposed endpoint like `/vision` or `/analyze` that Hermes (or any external app) could call to consume TeacherBOY's vision analysis. The vision logic lives inside agent classes (`profiler_agent.py`, `image_analyzer_agent.py`) and is triggered by LINE events, not HTTP requests to a vision API.

**Gap severity: HIGH.** The plan as stated requires either:
1. Reconfiguring Hermes to call the same underlying vision providers directly (Gemini, HF Inference, OpenRouter) — this is technically sound.
2. Building a new vision endpoint inside TeacherBOY (or a separate service) that wraps these providers — this changes the scope significantly.
3. Calling the TeacherBOY space's `/webhook` with image payloads — wrong protocol (LINE SDK format, requires LINE signature validation, would not return structured vision responses).

---

## Dependency Audit — Vision Pipeline

| Provider | Config Key | Default Model | Status in Config | Notes |
|---|---|---|---|---|
| Gemini | `gemini_vision_model` | `gemini-2.5-flash` | Configured (key required) | Primary vision provider; open source not required |
| HF Inference | `hf_inference_vision_model` | `meta/llama-3.2-90b-vision-instruct` | Configured (token required) | Free serverless vision via `api-inference.huggingface.co` |
| OpenRouter | `openrouter_vision_model` | `google/gemini-flash-1.5` | Configured (key required) | Fallback; must be free-tier model per config |
| Hermes | `hermes_vision_model` (implied) | — | Optional | Not explicitly set; `hermes_service` handles vision |
| NOUS Portal | `nous_vision_model` | — | Optional | Free vision AI endpoint |

**Key finding:** The `hf_inference_vision_model` points to `meta/llama-3.2-90b-vision-instruct` — a large multimodal model. This is the closest the project has to a "default vision model" definition, but it requires an HF token and hits the serverless rate limits.

---

## Best Practices — Code Quality (Brief)

- **Good:** Pydantic Settings (`src/config.py`, 1203 lines) with validation; environment-based config; `is_any_vision_provider_configured()` checks all vision paths.
- **Good:** Fallback chain (`llm_fallback_provider_priority`) — gemini → hermes → openrouter → nous — applies to LLM; vision uses similar provider selection.
- **Good:** Agent router (`agent_router.py`) separates concerns; vision agents (`ProfilerAgent`, `ImageAnalyzerAgent`) are isolated and can be disabled independently.
- **Warn:** No dedicated vision endpoint exposed externally; vision is tightly coupled to LINE message handling.
- **Warn:** Configuration validates `EvilEvan/teacherboy-*` namespace (`validate_evilevan_repo_namespace`) — any external service referencing different namespace would break.

---

## Optimality — Vision Approach

- **Current algorithm:** Priority-based agent routing → vision agent triggered by image events → vision model called with optimized prompts (`use_optimized_prompts=True` → 60-70% token reduction) → result returned to LINE.
- **Alternative for Hermes adoption:** Instead of adopting the space, Hermes should adopt the **provider configuration** from TeacherBOY — specifically the `gemini_vision_model` (`gemini-2.5-flash`) and the `hf_inference_vision_model` (`llama-3.2-90b-vision`) as its own vision endpoints. This avoids protocol mismatch.
- **Scalability:** Calling the HF Space's `/webhook` would add LINE SDK overhead, webhook validation latency, and no structured response format — not scalable for Hermes.

---

## Diagrams

See existing architecture files in `docs/`:
- `docs/backend-architecture.mmd`
- `docs/frontend-architecture.mmd`
- `docs/research-findings.mmd`
- `docs/entire-project.mmd`

These cover the full project architecture. For this vision-specific plan, the critical diagram is the provider chain shown in `docs/entire-project.mmd` (Gemini → HF Inference → OpenRouter → NOUS → Hermes).

---

## Findings Summary

1. **HIGH — Conceptual mismatch:** TeacherBOY space = LINE bot app; not a vision inference endpoint. (Source: `docs/architecture/overview.md`, `README.md`, deployment guide.)
2. **HIGH — No exposed vision endpoint:** No `/vision`, `/analyze`, or similar endpoint exists in the FastAPI app. (Source: `src/main.py`, `docs/guides/deployment.md`.)
3. **MEDIUM — Vision models are well-configured:** Config defines 5 vision-capable providers with model IDs. (Source: `src/config.py`, lines 196-324, 549-587.)
4. **LOW — Namespace validation locks repo IDs to `EvilEvan/teacherboy-*`: Any external reference needs to match. (Source: `src/config.py`, `_validate_evilevan_repo_namespace`.)
5. **GOOD — Engineering practices strong:** Typed async Python, Pydantic settings, agent isolation, optimized prompts. (Source: `docs/optimization-report-2026-06-13.md`.)

---

## Recommendations (Actionable, Prioritized)

### Priority: HIGH

**RECOMMENDATION 1: Clarify scope — adopt vision providers directly, not the space.**
- **Why:** The space is an app, not a service endpoint. Calling it for vision is architecturally wrong.
- **What:** Configure Hermes (and future apps) to use the same vision providers that TeacherBOY uses: `gemini-2.5-flash` (Gemini API key from env) as primary, `meta/llama-3.2-90b-vision-instruct` (HF token) as fallback, `openai/gpt-4o` (OpenRouter) as profiler-level vision.
- **Effort:** Low (config-only change; no code build required unless new endpoint needed).
- **Source:** `src/config.py`, `docs/optimization-report-2026-06-13.md`, architecture docs.

**RECOMMENDATION 2: If you actually want the space as a vision service, build a vision endpoint.**
- **Why:** If the real goal is to have `https://huggingface.co/spaces/EvilEvan/TeacherBOY` respond to vision requests from Hermes, a new FastAPI endpoint is needed.
- **What:** Add `/vision/analyze` (or similar) to `src/main.py` that accepts image + text, routes through `ProfilerAgent` / `ImageAnalyzerAgent`, and returns structured JSON (not LINE SDK format). Deploy via `git push hf HEAD:main`.
- **Effort:** Medium (2-4 days; requires endpoint design, auth, response format, testing).
- **Source:** `docs/guides/deployment.md`, `src/main.py`, agent router contract.

### Priority: MEDIUM

**RECOMMENDATION 3: Align Hermes vision config with TeacherBOY defaults.**
- **Why:** Keeps vision behavior consistent across apps.
- **What:** Set Hermes vision defaults to match TeacherBOY config:
  - Vision model: `gemini-2.5-flash` (or `gemini-2.5-flash` for vision tasks per `gemini_vision_model`)
  - Temperature: 1.15 (from `llm_temperature` — warm, creative responses)
  - Optimized prompts: enabled (`use_optimized_prompts=True`)
- **Effort:** Very low (env/config update).
- **Source:** `src/config.py` (lines 339-344, 630-633).

### Priority: LOW

**RECOMMENDATION 4: Document the vision provider chain in Hermes docs.**
- **Why:** Prevents future confusion between "using TeacherBOY space" and "using TeacherBOY's vision providers."
- **What:** Add a `VISION.md` or section in `~/.hermes/TOOLS.md` referencing this plan and the provider chain.
- **Effort:** Very low (30 min).
- **Source:** This investigation.

---

## Interactive / Follow-up

If you want me to implement this (Project-Manager mode) — tell me which recommendation:
- **Option A:** Config-only — wire Hermes vision config to match TeacherBOY providers (Recommendation 1 + 3). No space changes.
- **Option B:** Endpoint build — add `/vision/analyze` to TeacherBOY and deploy to HF space (Recommendation 2).
- **Option C:** Full audit — run full surgical-investigation on Hermes vision module before deciding.

Confirm before I proceed. 🐺


---

## IMPLEMENTATION NOTE (2026-09-17)
Direct edit of `~/.hermes/config.yaml` blocked (security-sensitive file). Vision config change documented: 
- Current: `provider: kilo` / `model: nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free`
- Target (aligned with TeacherBOY): `provider: openrouter` / `model: google/gemini-2.5-flash:free`
- Temperature: 1.15 (from `llm_temperature` in `src/config.py`)
- Optimized prompts: `use_optimized_prompts=True`
- Reusable for future apps via same config block under `auxiliary.vision`.
Apply with: `hermes config set auxiliary.vision.provider openrouter` (or edit `.hermes/config.yaml` manually).
