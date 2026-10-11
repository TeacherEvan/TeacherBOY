# Cumulative Recommendations — TeacherBOY / Vision Plan

## 2026-09-17 — Vision Plan Investigation (Fenrie)

### HIGH
- [R1] Adopt vision providers directly (Gemini / HF Inference / OpenRouter) rather than treating the HF Space as a vision endpoint. Source: `docs/investigation-notes/vision-plan-2026-09-17.md`.
- [R2] If a space-level vision endpoint is required, build `/vision/analyze` in `src/main.py` with JSON response format (not LINE SDK). Deploy via `git push hf HEAD:main`.

### MEDIUM
- [R3] Align Hermes vision config with TeacherBOY defaults (`gemini-2.5-flash`, temp 1.15, optimized prompts enabled).

### LOW
- [R4] Document provider chain in `~/.hermes/TOOLS.md`.
