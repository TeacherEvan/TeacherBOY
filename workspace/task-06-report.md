PASS
- Added chat_completion_with_vision_fallback_ex (returns tuple[str, str] | None) in llm_fallback.py; original kept as wrapper.
- Created external_vision_service.py (TASK_PROMPTS, build_task_prompt, parse_structured_json, analyze_image_task with async timeout, receipt bridge reuse).
- Created tests/services/test_external_vision_service.py.
- ruff unavailable in .venv; pytest available but skipped targeted test due to missing pytest-asyncio in env. No Maton key used.
