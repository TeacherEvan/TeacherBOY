
### Verify Visual & Transform Claims (Task 11)

- [ ] **Visual claim:** HF Space page shows the new commit; `/api/v1/tasks` answers with the task list; OCR smoke response contains the drawn text.
- [ ] **Transform claim:** Space SHA == new HEAD; run log noise counts drop to 0; `/health` shows `external_api.enabled: true`.
- [ ] **Verification method:** the curl/python outputs above, saved into the PR/issue notes.
- [ ] **Verification result:** [PASS / FAIL / BLOCKED — evidence snippet]

---

## Self-Review (run 2026-09-22 before saving)

**1. Spec coverage:** Every finding F1–F9 maps to a task — F1/F2 → Task 2; F3 → Task 3; F4/F6 → Task 1; F5 → Task 4; F7 → Task 10; F8 (the One Change) → Tasks 5–9; F9 → recorded in the backlog below (intentionally not built; no live-log evidence of user impact). The 2026-09-17 investigation's R2 ("build `/vision/analyze` … JSON response format") is delivered as `/api/v1/analyze` with stronger auth/limits.

**2. Placeholder scan:** No TBD/TODO/"handle edge cases" steps; every code step carries the full code to paste. The only operational unknowns are flagged as explicit human actions (Space secret provisioning in Task 11 Step 4).

**3. Type consistency:** Names used consistently across tasks — `silence_noisy_loggers`, `IpRateLimiter.allow/clear`, `chat_completion_with_vision_fallback_ex -> tuple[str, str] | None`, `SUPPORTED_TASKS`, `analyze_image_task(**kwargs) -> dict`, router accessors `_expected_token` etc., config helpers `get_external_api_token()/get_external_api_image_hosts()`, response keys `success/requestId/bytes/task/text/structured/ocr/provider/latency_ms`. Task 8's tests patch exactly the accessor names defined in Task 8's implementation.

**4. Visual/Transform verification completeness:** Every user-observable change has an observation method: log content (Tasks 2, 3, 11), dataset tree (Task 4), live HTTP endpoints (Tasks 9, 11), OCR round-trip on real infrastructure (Task 11 Step 6). No change relies on "tests pass" alone.

**5. Anti-Gravity collaboration boundary:** N/A — no external agent involved. Sharing rules stated in the header for any future sharing (no secrets, no user data, repo files only).

**6. Source provenance check:** All referenced internals verified in-repo on 2026-09-22 (file:line noted in findings); external doc claims (huggingface-hub 0.23.0 `ignore_patterns` on `CommitScheduler`) match the pinned dependency in `requirements.txt:35`; HF API endpoints were exercised live during investigation (space meta, dataset tree, logs).

---

## Backlog (found, deliberately NOT built now)

- `ReceiptAgent._is_user_linked` TODO — implement the Budget Boss linked-users check before enabling `RECEIPT_REQUIRE_LINKED` (security).
- Webhook per-IP limiter dict (`main.py:1404`) grows per unique IP; consider moving to the new `IpRateLimiter` with periodic `clear()` on a timer.
- Bangkok Post feeds: consider adding a second Thai source or per-feed disable list if 451 persists; the current fix only silences the log noise.
- `/receipt/scan` could become a thin wrapper over `/api/v1/analyze` with `ingest` semantics once Budget Boss migrates.
- Rotate the ExchangeRate-API key (it appeared in run logs before Task 2 lands) — operational action in the HF account.

## Execution Handoff

Two execution options:

1. **Subagent-Driven (recommended)** — one fresh subagent per task, review between tasks, fast iteration. Tasks 1–8 are small and independent; the subagent pattern keeps each change reviewed against its verification block.
2. **Inline Execution** — run the tasks in this session with `executing-plans`, batch checkpoints after Part A (Tasks 0–4) and Part B (Tasks 5–9) for review.

Either way, Task 11 (deploy + live smoke) should run last, with Evan watching the HF Space settings when the token step comes up.