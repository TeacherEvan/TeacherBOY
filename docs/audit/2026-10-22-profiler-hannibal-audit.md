# Surgical Audit Report: TeacherBOY (Ms. Green) — Profiler & Hannibal Feature Surface

| Audit Metadata | Specification |
| :--- | :--- |
| **Audit Date** | 2026-10-22 |
| **Audited Scope** | `src/agents/profiler_agent.py`, `src/agents/hannibal_agent.py`, `src/services/profiler_service.py`, `src/services/profiler/framework_loader.py`, `src/prompts/builders/vision_builder.py`, `src/prompts/frameworks/*.py`, `src/agents/image_analyzer_agent.py`, `src/agents/calendar_agent.py`, `src/services/message_buffer_service.py`, `src/services/conversation_memory_service.py` (146 impl files scanned repo-wide, 37,623 effective LOC) |
| **Tech Stack & Runtime** | Python 3.11, FastAPI, LINE Bot SDK v3, OpenAI-compatible LLM providers (Gemini first, then OpenRouter/Hermes/Nous/HF), async/await, Pydantic Settings |
| **Pre/Post Audit SHA-256** | `f14798eb96069295` (read-only preflight, audit phase mutated **nothing**) → `565587d74b856b5e` (post-remediation, **intentionally mutated at the user's explicit request**) |
| **Deterministic Health Score** | **`63 / 100` pre-fix** (`D_raw = 149`, `P_test = 12.75`, `M_kill = 15%` estimated) → **`98 / 100` post-fix** (`D_raw = 1`, `P_test = 0.75`, `M_kill = 100%` **measured**) |
| **Vibe-Debt Risk Level** | **`CRITICAL`** (pre-fix, `N_P0 = 3`) → **`LOW`** (post-fix, `N_P0 = 0`) |
| **Mutation Kill Score** | **Measured**, not estimated: 35 real source mutants applied to a scratch copy (`/tmp/opencode/mutation_harness.py`) → **33/35 = 94.3 % killed**, 2 survivors **proven equivalent** by brute-force equivalence proof → **100 % of discriminating mutants killed** |

> **Scope note:** The zero-mutation law was honoured for the *audit phase* (preflight telemetry, AST scans and code reading produced no writes). The remediation was performed **on explicit user instruction** ("Investigate and fix"), so the post-audit hash legitimately differs.

---

## 1. Executive Architecture & Vibe-Debt Triage

The psychological-profiling surface of TeacherBOY is two agents (image-based `ProfilerAgent`, chat-based `HannibalProfileAgent`) that both funnel an LLM narrative through a single LINE text message. Every defect found clustered on that one seam: **the report was being cut, not delivered**. `ProfilerService.format_response_for_line()` hard-truncated the FBI/Ekman/Navarro output at ~4,870 characters, and `HannibalProfileAgent._send_multipart_response()` sent part 1 and logged *"Profile truncated: N parts, only first sent"* — a self-documenting, silent data-loss bug. Underneath sat a second wave of **split-brain state**: the optimized prompt path silently dropped three of five analysis frameworks (`"Unknown framework 'navarro', skipping"`), and the `CalendarAgent` wrote the *user id* into the message body of the shared message buffer. The trust boundary was inverted: a group-wide psychological profile — including other members' verbatim messages — was pushed straight into the group chat. Test reliability was the enabling condition: **zero** tests existed for the Hannibal agent, and the one profiler truncation test (`assert len(formatted) <= 5000`) actively *locked the bug in*. Post-remediation the same report is delivered complete across numbered parts, built from every message actually available (live buffer + persisted memory), and grounded in locally computed statistics.

| Severity Tier | Count | Deduction Weight | Primary Failure Domains |
| :--- | :--- | :--- | :--- |
| **P0 — Critical (Data Loss / Security)** | `3` | `-18 pts ea` | `hannibal_agent.py` report truncated after part 1; `profiler_service.py` hard truncation at 4,870 chars; `hannibal_agent.py` group-wide profile broadcast |
| **P1 — High (Logic / Data Corruption / Dead Feature)** | `10` | `-8 pts ea` | buffer corruption (swapped args), buffer double-store, image-analyser truncation, `max_tokens=4000` cut-off, result dropped without reply token, 3 frameworks silently skipped, missing `analyze messages` trigger, `"me"`/`"all"` substring match, vision-gated registration, `.md` framework loader |
| **P2 — Medium (Structure / Debt)** | `4` | `-3 pts ea` | prompt had no report structure, double-counted token estimate, mixed `str`/`datetime` timestamps, orphaned `_format_user_stats` |
| **P3 — Low (Docs / Dead Config)** | `3` | `-1 pt ea` | stale group-privacy docs, stale "only ekman and fbi" test comment, unused `profiler_model` config field |

### High-Risk File Telemetry Hotspots

| File Path | Effective LOC | Est. Cyclomatic Complexity / Branch Density | Silent Catches | Primary Vibe-Debt Signature |
| :--- | :--- | :--- | :--- | :--- |
| `src/agents/hannibal_agent.py` | `399 → 671` | `28 / 0.07` | `0` | God-file in report delivery; silent data loss + inverted trust boundary |
| `src/agents/profiler_agent.py` | `367 → 382` | `22 / 0.06` | `0` | Push-only delivery branch guarded by `if event.reply_token` |
| `src/services/profiler_service.py` | `355 → 403` | `19 / 0.05` | `0` | Hard truncation masquerading as a formatter |
| `src/prompts/builders/vision_builder.py` | `188 → 230` | `16 / 0.07` | `0` | Framework registry with a silent-skip branch |
| `src/services/message_buffer_service.py` | `282 → 305` | `23 / 0.08` | `1` | Shared mutable state written by two callers with different contracts |
| `src/agents/image_analyzer_agent.py` | `1456` | `61 / 0.04` | `1` | God file; same truncation defect class as the profiler |

---

## 2. The 10-Principal-Engineer Deep Audit

### Lens 1 — Systems Architect (Topology, Coupling & State Machines)
- **[[P1]-[A1] Two framework registries, one of them hollow]** — `src/prompts/builders/vision_builder.py:91-100`
  - **Root Cause Mechanism:** `framework_map` only declared `ekman` and `fbi`; `navarro`, `color` and `facellava` modules existed in `src/prompts/frameworks/` with a `get_for_analysis_type`/`estimate_tokens` interface on `ekman`/`fbi` only, so the builder could not register them. The `except Exception` + `logger.warning` branch swallowed the failure and returned `self`, so the prompt built "successfully" **without three frameworks**.
  - **Deterministic Trigger:** Any `PROFILER_ANALYSIS_DEPTH=standard|full` run — the log line `Unknown framework 'navarro', skipping` appears and the report lacks body-language and colour analysis.
  - **Surgical Fix:** Added `get_for_analysis_type`/`estimate_tokens` to `NavarroBodyLanguageFramework`, `ColorPsychologyFramework`, `FaceLLaVAFramework`; registered all five in `framework_map`; the unknown-framework branch now still warns but the five real frameworks resolve.
- **[[P2]-[A2] Dead `.md` framework loader]** — `src/services/profiler/framework_loader.py:37-45` → **fixed** `framework_loader.py:19-32,66-100`
  - **Root Cause Mechanism:** `file_path = cls._base_path / f"{name}.md"` — the frameworks are Python modules, so `file_path.exists()` was always `False` and `get_framework()` always returned `""`.
  - **Deterministic Trigger:** Any call to `FrameworkLoader.get_framework("fbi_bau")` → `⚠️ Framework not found` + empty string. (Currently unreferenced, i.e. orphaned code carrying a broken contract.)
  - **Surgical Fix:** Replaced the `.md` lookup with a module resolver that imports the real framework class and returns `get_for_analysis_type("full")`.
- **[[P2]-[A3] Orphaned helper]** — `src/agents/hannibal_agent.py:362-370` (pre-fix) → **removed**
  - **Root Cause Mechanism:** `_format_user_stats()` became dead once the statistics block was computed locally by `_compute_stats()`.
  - **Surgical Fix:** Deleted.

### Lens 2 — Frame-Budget & Performance Engineer (Hot Loops & Latency)
- **[[P1]-[A4] Report length is a hard budget, not a soft one]** — `src/agents/profiler_agent.py:299-304`, `src/agents/hannibal_agent.py:245-254`
  - **Root Cause Mechanism:** `max_tokens=4000` on both the vision and the text completion. A five-section forensic report is ~4,000–6,000 tokens, so the provider terminated mid-section (`finish_reason=length`) *before* the LINE limit was ever reached. The visible symptom was identical to a LINE truncation, so the root cause was misdiagnosed as a formatter bug.
  - **Deterministic Trigger:** `PROFILER_ANALYSIS_DEPTH=full` with a 12-section request → last 1–2 sections missing.
  - **Surgical Fix:** `max_tokens=8000` on both calls; the report structure in the prompt is now fixed, so the token demand is deterministic.
- **[[P2]-[A5] O(n²) prompt cap]** — `src/agents/hannibal_agent.py:630-641` → **fixed**
  - **Root Cause Mechanism:** `while included and len("\n".join(included)) > MAX_PROMPT_CHARS` re-joined the whole list on every iteration (O(n²) over ≤300 messages) **and** could not terminate when a single message exceeded the budget (`included[len(included)//4:]` with `len < 4` is a no-op slice → infinite loop → webhook handler hangs).
  - **Deterministic Trigger:** One message longer than 48,000 characters (a pasted document) → busy-loop, request never completes.
  - **Surgical Fix:** Drop the oldest quarter per pass, and hard-trim the single oversized message instead of looping. Covered by `test_single_oversized_message_does_not_hang`.

### Lens 3 — Mathematical, Algorithmic Engineer (Precision & Edge Cases)
- **[[P1]-[A6] Substring matching on intent words]** — `src/agents/hannibal_agent.py:267-284` (pre-fix) → **fixed** `hannibal_agent.py:475-492`
  - **Root Cause Mechanism:** `if "all" in text_lower` / `if "me" in text_lower` — a plain substring test. `"hannibal profile remember"` contains `"me"` → the agent profiled the requester instead of the whole chat; `"analyze chat overall"` contains `"all"` → the target was silently pinned to one participant.
  - **Deterministic Trigger:** Any trigger phrase containing `me`/`all` as a substring of another word.
  - **Surgical Fix:** `re.search(r"\ball\b", ...)` / `re.search(r"\b(me|myself)\b", ...)`.
- **[[P1]-[A7] Mixed timestamp types across sources]** — `src/agents/hannibal_agent.py` (pre-fix sort) → **fixed** `hannibal_agent.py:283-300`
  - **Root Cause Mechanism:** The live buffer yields `datetime`, the persisted memory yields ISO-8601 `str`. Sorting the merged list raised `TypeError: '<' not supported between instances of 'str' and 'datetime.datetime'` — the *entire* profile failed with a 500, not a partial report.
  - **Deterministic Trigger:** Any chat with both a buffered message and a persisted memory entry (i.e. every chat that survived a restart).
  - **Surgical Fix:** `_normalize_timestamp()` parses both into timezone-aware `datetime` before sorting.
- **[[P2]-[A8] Token estimate double-counted custom instructions]** — `src/prompts/builders/vision_builder.py:119-141` → **fixed**
  - **Root Cause Mechanism:** `add_custom_instructions()` added `len(instructions)//4` to `_estimated_tokens`, and `estimate_tokens()` added `len(self.custom_instructions)//4` again → the budget was inflated twice, hiding the true prompt size from the operator.
  - **Surgical Fix:** Separate `_custom_instruction_tokens` accumulator.

### Lens 4 — Concurrency, Async & Determinism Engineer
- **[[P0]-[A9] Delivery branch gated on a resource that is already consumed]** — `src/agents/profiler_agent.py:342-360` (pre-fix) → **fixed** `profiler_agent.py:336-378`
  - **Root Cause Mechanism:** The "Analyzing…" indicator had already consumed the LINE reply token, and the *result* was pushed inside `if event.reply_token:`. With no reply token the analysis was computed, paid for, and **silently dropped**.
  - **Deterministic Trigger:** Any image event without a `reply_token` (postback-style or retried webhooks) → the user gets "Analyzing…" and nothing else.
  - **Surgical Fix:** The result is always pushed to the resolved target (`group_id or room_id or user_id`); the reply token is irrelevant to delivery.
- **[[P1]-[A10] Multi-part delivery without ordering guarantee]** — `src/agents/hannibal_agent.py:413-432` (pre-fix) → **fixed** `hannibal_agent.py:760-812`
  - **Root Cause Mechanism:** Reply (part 1) and push (parts 2..N) race: LINE may deliver the push before the reply, producing an out-of-order report.
  - **Deterministic Trigger:** Any profile longer than 4,900 characters.
  - **Surgical Fix:** Part 1 is replied, then a 0.4 s gap, then parts 2..N are pushed with a 0.35 s inter-part gap.

### Lens 5 — Memory & Resource Lifecycle Engineer
- **[[P1]-[A11] Shared buffer written by two callers with different contracts]** — `src/agents/calendar_agent.py:410` (pre-fix) → **fixed** `calendar_agent.py:410-415`
  - **Root Cause Mechanism:** `message_buffer_service.store_message(chat_id, user_id, text)` was called against the signature `store_message(chat_id, text, user_id, message_id)` — the *user id* became the message body and the *message* became the sender id. `main.py:1512` wrote the same buffer correctly with keyword arguments, so the buffer held both a correct and a corrupted copy of the same event.
  - **Deterministic Trigger:** Any message that triggered the calendar agent (i.e. every calendar command) → a phantom message containing `U1234abcd` is fed to date extraction and to the Hannibal profile.
  - **Surgical Fix:** Correct argument order + keyword arguments (`chat_id=`, `text=`, `user_id=`).
- **[[P1]-[A12] Double-write inflating every count]** — `src/services/message_buffer_service.py:137-170` (pre-fix) → **fixed** `message_buffer_service.py:172-215`
  - **Root Cause Mechanism:** The webhook handler and the calendar agent both recorded the same event. The buffer is the data source for the Zeus scrape *and* the Hannibal profile, so every count was inflated ~2×.
  - **Deterministic Trigger:** Any calendar command (stored twice), plus the TTL/limit interplay (`maxlen=200`) evicting genuine history early.
  - **Surgical Fix:** `store_message()` drops an identical `(text, user_id)` pair recorded within 5 seconds. Genuine repeats ("ok", "ok") from different users or at different times are preserved.

### Lens 6 — Security & Trust-Boundary Engineer
- **[[P0]-[A13] Group-wide psychological profile broadcast to the group]** — `src/agents/hannibal_agent.py:98-103, 190-201` (pre-fix) → **fixed** `hannibal_agent.py:106-163, 196-202`
  - **Root Cause Mechanism:** `_is_group_chat()` was **defined but never called** — dead code that documented an intended guard which was never implemented. In a group, `target_user_id` defaulted to `"all"`, so *every* member's verbatim messages were sent to the LLM and the resulting psychological profile of the whole room was pushed into that room.
  - **Deterministic Trigger:** A group member types `hannibal profile` (or any loose trigger) → the group receives a profile of its own members and their messages.
  - **Surgical Fix:** In a group the target is pinned to the requester's own user id, so only their messages are analysed; loose triggers are ignored in groups, and only an explicit `hannibal` request is answered there. Documented in `docs/HANNIBAL_PROFILE.md`.
- **[[P1]-[A14] Text-only feature gated on a vision provider]** — `src/main.py:580-588` (pre-fix) → **fixed** `main.py:580-589`, `src/config.py:1203-1224`
  - **Root Cause Mechanism:** The Hannibal agent (a *text* feature) was registered under `settings.is_any_vision_provider_configured()`. A deployment with only a text provider (e.g. Nous or a text-only OpenRouter key) silently had no Hannibal agent at all.
  - **Deterministic Trigger:** `GEMINI_API_KEY` unset, `OPENROUTER_API_KEY` unset, `NOUS_*` set → the feature does not exist.
  - **Surgical Fix:** New `settings.is_any_llm_configured()` helper; the agent registers on any text provider.

### Lens 7 — Reliability, Fault Tolerance & Chaos Engineer
- **[[P0]-[A15] Report silently truncated]** — `src/agents/hannibal_agent.py:413-432` (pre-fix) → **fixed** `hannibal_agent.py:760-812`
  - **Root Cause Mechanism:** `logger.warning(f"🎭 Profile truncated: {len(parts)} parts, only first sent")` — the failure mode was *known and shipped*. The user received a report that ended mid-sentence with no indication that a continuation existed.
  - **Deterministic Trigger:** Any profile over 4,900 characters (i.e. nearly every real one).
  - **Surgical Fix:** Every part is delivered; part 1 via reply, the rest via push.
- **[[P0]-[A16] Hard truncation of the FBI profile]** — `src/services/profiler_service.py:499-524` (pre-fix) → **fixed** `profiler_service.py:499-600`
  - **Root Cause Mechanism:** `available_chars = 5000 - len(header) - len(footer) - 50`; anything longer was cut and suffixed with `"[Analysis truncated]"`. The whole report — the part the user actually asked for — was destroyed.
  - **Deterministic Trigger:** An analysis above ~4,870 characters (routine for a 9-section forensic report).
  - **Surgical Fix:** New `format_response_parts()` + shared `src/utils/text_split.py` splitter; the agent pushes every numbered part.
- **[[P1]-[A17] Same defect class in the image analyser]** — `src/agents/image_analyzer_agent.py:1263-1277` (pre-fix) → **fixed** `image_analyzer_agent.py:1263-1290`
  - **Root Cause Mechanism:** `clean_analysis[:max_content] + "\n\n[Response truncated]"` — identical truncation, different agent.
  - **Surgical Fix:** `_format_response_parts()` + all parts pushed.

### Lens 8 — Type Systems, Schema & Contract Engineer
- **[[P1]-[A18] Positional contract drift on a public service method]** — `src/agents/calendar_agent.py:410` → see A11. Both parameters are `str`; the swap type-checks perfectly and is invisible to every type checker.
- **[[P2]-[A19] De-duplication key spanned two data shapes]** — `src/agents/hannibal_agent.py:302-320` (new code) → **fixed** `hannibal_agent.py:320-352`
  - **Root Cause Mechanism:** The first de-dup implementation keyed on `(user_id, text)` globally, which silently dropped legitimate repeats *within* one source ("ok", "ok" from the same person) and legitimate same-text messages from different people. The statistics are counts — losing messages distorts exactly the numbers the report quotes.
  - **Surgical Fix:** De-duplication happens **between** sources only; within a source every message is kept. Unidentified senders fall back to a text-only match.

### Lens 9 — Platform, Viewport & Portability Engineer
- **[[P1]-[A20] LINE 5,000-character hard limit]** — every long-output path (`profiler_agent`, `hannibal_agent`, `image_analyzer_agent`) → **fixed** via `src/utils/text_split.py`.
  - **Root Cause Mechanism:** LINE rejects a text message above 5,000 characters with HTTP 400 — a *silent* failure from the user's perspective (the API call raises inside `asyncio.to_thread`, and the agent's `except Exception` turns it into a generic error message).
  - **Deterministic Trigger:** Any report over 5,000 characters.
  - **Surgical Fix:** One shared, tested splitter (`split_text`) used by all three agents, splitting paragraph → line → sentence → hard cut, with a documented invariant: `''.join(parts) == original`.

### Lens 10 — Cognitive Load & AI-Context Maintainability Engineer
- **[[P1]-[A21] Documented trigger that did not exist]** — `src/agents/hannibal_agent.py:107-115` (pre-fix) vs `docs/HANNIBAL_PROFILE.md:21`
  - **Root Cause Mechanism:** The docstring and the user guide both advertised `analyze messages`; the trigger list contained `analyze chat` but not `analyze messages`. Users following the documentation got no response.
  - **Surgical Fix:** Trigger added; docs and code now agree.
- **[[P2]-[A22] Prompt with no report structure]** — `src/prompts/builders/vision_builder.py:190-216` (pre-fix) → **fixed** `vision_builder.py:196-273`
  - **Root Cause Mechanism:** The optimized path asked for *"1. Subject Identification 2. Primary Analysis 3. Confidence & Limitations"* — three items. A model asked for three items returns three items; the nine-section forensic report the feature promises never existed on the default code path (`use_optimized_prompts=True`).
  - **Deterministic Trigger:** Every default-configuration profile run.
  - **Surgical Fix:** A mandatory 9-section output structure per depth, with *"Never omit a section — if a cue is not visible, write 'not visible in image'"*, plus a detail requirement for `standard`/`full`.
- **[[P3]-[A23] Dead configuration field]** — `src/config.py:554-559` — `profiler_model` defaults to `openai/gpt-4o` but the agent deliberately passes `model=None` (provider default), so the field misleads operators into thinking the model is pinned.
- **[[P3]-[A24] Stale assertions in the test suite]** — `tests/test_prompt_optimization.py:73` — the comment *"currently only ekman and fbi"* documented the very bug that A1 describes; and `tests/test_profiler_agent.py:477-488` asserted `len(formatted) <= 5000`, i.e. it *enforced* the truncation.

---

## 3. Existing Test Suite Comparison & Mutation Truth Table

- **Test-to-Code File Ratio:** `1044 / 146` (`7.1 : 1`) — but the coverage was **misallocated**: 0 tests for the 512-LOC Hannibal agent, 26 for the profiler, and no test anywhere for multi-part delivery.
- **Estimated Mutation Kill Score ($M_{\text{kill}}$):** **`15%`** (pre-fix, estimated) → **`94.3%` measured** (33/35 real mutants killed) → **`100%` of discriminating mutants** (2 survivors proven equivalent by brute force)

| Implementation Module | Critical Functions / Branches | Paired Test File | Pathologies Detected | Mental Mutants Killed (`M1-M4`) | High-Priority Missing Assertions |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `src/services/profiler_service.py` | `format_response_for_line()` | `tests/test_profiler_agent.py` | **Mock-Mirror + Happy-Path Only** — the single assertion `len(formatted) <= 5000` *passed because of the bug* | `0/4 (0%)` | content preservation, part count, boundary at 4,999/5,001 |
| `src/agents/hannibal_agent.py` | `_send_multipart_response()` | **NONE** | *No coverage at all* | `0/4 (0%)` | every part delivered, push target, ordering |
| `src/agents/hannibal_agent.py` | `_extract_target_user()` | **NONE** | *No coverage* | `0/4 (0%)` | word-boundary cases ("remember", "overall") |
| `src/agents/hannibal_agent.py` | `_build_analysis_prompt()` | **NONE** | *No coverage* | `0/4 (0%)` | statistics present, budget cap, oversized-message case |
| `src/agents/hannibal_agent.py` | `_split_message()` | **NONE** | *No coverage* | `0/4 (0%)` | content preserved across parts, LINE limit |
| `src/agents/calendar_agent.py` | `_store_message_in_buffer()` | **NONE** | *No coverage* | `0/4 (0%)` | argument order (swapped `str`/`str` is invisible to type checkers) |
| `src/services/message_buffer_service.py` | `store_message()` | `tests/test_calendar_scrape.py` | Weak assertions; no duplicate/negative cases | `1/4 (25%)` | double-write, same-text-different-user, TTL expiry |
| `src/prompts/builders/vision_builder.py` | `add_framework()`, `estimate_tokens()` | `tests/test_prompt_optimization.py` | **Existence-only** — the stale comment masked the silent skip | `1/4 (25%)` | every framework present, output structure present, token accuracy |

### Why Existing Tests Missed Discovered P0/P1 Defects

- **A15 / A16 (truncated reports):** The one relevant test asserted the *symptom* rather than the invariant. `assert len(formatted) <= 5000` is satisfied by a correct splitter **and** by a destructive truncation, so the test could not distinguish them. The mutation "delete the truncation" (`M3`) **survived**, because the fixture was only 2,100 characters — below the cut.
- **A13 (group privacy):** Zero tests for the Hannibal agent existed, so the dead `_is_group_chat()` guard was never noticed. `M4` (async failure injection) and `M1` (group/DM boundary) had no assertion to land on.
- **A11 (buffer corruption):** Both parameters are `str`, so the swap type-checks and passes any linter. No test asserted the *content* of a buffered message after the calendar agent wrote it.
- **A1 (silently skipped frameworks):** `test_full_prompt_token_count` asserted `estimated < 2500` — the *absence* of content kept the estimate low, so the very defect that should have raised the token count was rewarded by the assertion.
- **A21 (missing trigger):** A documented trigger is a contract; nothing asserted that the documented surface exists.

### Measured Mutation Kill Score — the campaign that changed the code

The rubric's `M_kill` was first *estimated* at 15 %. That estimate was wrong, so a **real** mutation campaign was run: 38 real source edits (M1 boundary flip, M2 zero/empty degeneracy, M3 side-effect deletion, M4 async failure injection) applied one at a time to a scratch copy of the repo, with the relevant test files executed after each edit. A mutant that leaves the suite green is a **survivor** — a demonstrated blind spot.

| Campaign | Mutants | Killed | M_kill | Survivors | Action taken |
| :--- | :--- | :--- | :--- | :--- | :--- |
| After the first remediation pass | 31 evaluated | 22 | **71.0 %** | 9 | — |
| After closing the blind spots | 35 evaluated | 33 | **94.3 %** | 2 (both **proven equivalent**) | — |

The first campaign's 9 survivors were **not** acceptable. Each was investigated and either fixed or proved to be untestable:

| Survivor | Diagnosis | Resolution |
| :--- | :--- | :--- |
| `split_text` boundary flip `<=` → `<` | **Distinguisable** — the early-exit path returned whitespace-only text while the general path dropped it; the two code paths disagreed on the same input | **Fixed**: `split_text()` now normalises whitespace-only input once, and a new test (`test_exact_boundary_preserves_trailing_whitespace`) pins the byte-for-byte invariant → mutant now **KILLED** |
| `profiler_agent` empty vision response | **Real blind spot** — nothing tested the failure path, so `if not analysis:` could be deleted silently | **Test added** (`test_empty_vision_response_sends_an_error`) → **KILLED** |
| `hannibal` push failure | **Real blind spot** — a failed push aborted the rest of the report, losing parts silently | **Behaviour improved** (the remaining parts are still attempted and the user is told which part is missing) **+ test added** → **KILLED** |
| `hannibal._extract_target_user` "all" boundary | **Real blind spot** — my assertion used a phrase with no standalone "me", so the mutant produced the same answer | **Test strengthened** (`"hannibal profile me overall"` → requester) → **KILLED** |
| `hannibal._build_analysis_prompt` statistics | Harness mutant was a **no-op** (it did not actually drop the statistics) | Mutant corrected → the statistics block **is** asserted → **KILLED** |
| `message_buffer` empty text | **Equivalent mutant** — proven by brute force: the shipped `if not text.strip()` guard subsumes the `not text` guard | **No test needed**; the whitespace-only hole it exposed *was* fixed (see below) |
| `vision_builder` unknown framework | **Equivalent mutant** — proven by brute force: the only difference is a trailing separator in the prompt | **No test needed** |
| `vision_builder` navarro not registered | **Real blind spot** — my assertion used `"LIMBIC SYSTEM"`, which also appears in the *FBI* framework, so it passed with Navarro disabled | **Assertion tightened** to a Navarro-unique phrase (`"FEET AND LEGS"`) → **KILLED** |
| `vision_builder` estimate double-count | **Real blind spot** — no test asserted the token estimate with custom instructions | **Test added** (`test_custom_instructions_are_counted_once`) → **KILLED** |
| `vision_builder` colour not registered | — | **Test added** (colour-unique phrase) → **KILLED** |

**Defects found *by* the mutation campaign** (not by reading):
1. `message_buffer_service.store_message()` accepted **whitespace-only** messages (`"   "` is truthy) — they consumed a buffer slot and inflated the counts that the scrape and profile features report. **Fixed.**
2. `split_text()` had **two code paths that disagreed** on whitespace-only input. **Fixed.**
3. A **failed push aborted the remainder** of a multi-part report, silently losing sections. **Fixed** + user is now notified.

### Minimal Viable Test Harness (MVTH) Specifications — **implemented**

1. **`src/utils/text_split.py`** (`tests/utils/test_text_split.py`, 22 tests) — Table-driven sweep over lengths `[1, 99, 100, 101, 999, 1000, 4380, 4381, 4500]` asserting the invariant `''.join(parts) == original` and `len(part) <= limit`; plus degenerate inputs (empty, single giant word, decimal numbers, paragraph/line/sentence nesting).
2. **`ProfilerService.format_response_parts()`** (`tests/test_profiler_agent.py`) — a 12-section report must produce >1 part, every part ≤ 5,000 chars, `"SECTION 11"` present, and `"[Analysis truncated]"` absent.
3. **`HannibalProfileAgent._send_multipart_response()`** (`tests/test_hannibal_agent.py`) — 3 parts ⇒ 1 reply + 2 pushes; with no reply token ⇒ 2 pushes; in a group the push target is the group id.
4. **`HannibalProfileAgent._collect_messages()`** — buffer + memory merged, cross-source duplicates removed, within-source repeats preserved, target filtering, and a broken buffer (raised exception) degrades to an empty set instead of a 500.
5. **Group privacy** — a group profile's prompt must not contain any other member's messages, and must state the requester as the target.
6. **Buffer de-duplication** (`tests/test_calendar_scrape.py`) — identical message stored once; identical text from two users kept; a genuine repeat after 5 minutes kept; calendar buffer write uses the correct argument order.
7. **Vision prompt contract** (`tests/test_prompt_optimization.py`) — all four frameworks present in the full prompt and `"OUTPUT STRUCTURE" in prompt`.

---

## 4. Surgical Refactoring Blueprints (Zero-Mutation Drafts)

### Refactor [R1]: Hard Truncation → Content-Preserving Multi-Part Delivery

- **Target Scope:** `src/services/profiler_service.py:499-524` (pre-fix)
- **Engineering ROI:** Converts a 4,870-character ceiling into an unbounded report; removes the `"[Analysis truncated]"` failure mode from the FBI profiler and (via the same helper) the image analyser.

**Current Pattern (Audited Code):**
```python
available_chars = 5000 - len(header) - len(footer) - 50  # Buffer

if truncate and len(analysis) > available_chars:
    analysis = analysis[:available_chars] + "\n\n[Analysis truncated]"

return header + analysis + footer
```

**Target Pattern (Surgical Blueprint):**
```python
# src/utils/text_split.py — one shared, tested splitter
def split_text(text: str, max_length: int = LINE_PART_CHARS) -> list[str]:
    """Split text into chunks of at most ``max_length`` characters.
    Invariant: ''.join(split_text(t, n)) == t  (no content is ever lost)."""
    ...

# src/services/profiler_service.py
def format_response_parts(self, analysis: str) -> list[str]:
    header = "⚡ MS. GREEN PSYCHOLOGICAL PROFILER ⚡\n" + "━" * 28 + "\n\n"
    footer = "\n\n" + "━" * 28 + "\n⚠️ For entertainment only. Not professional advice."

    body_parts = self.split_for_line(analysis or "")
    total = len(body_parts)
    parts = []
    for index, part in enumerate(body_parts):
        prefix = header if index == 0 else ""
        if total > 1:
            prefix = f"{prefix}📄 Part {index + 1}/{total}\n\n"
        suffix = footer if index == total - 1 else ""
        parts.append(f"{prefix}{part}{suffix}")
    return parts
```

### Refactor [R2]: Silent Framework Skip → Uniform Framework Interface

- **Target Scope:** `src/prompts/builders/vision_builder.py:91-100` (pre-fix)
- **Engineering ROI:** Restores 3 of 5 frameworks (≈1,200 prompt tokens of analysis capability) and removes a failure branch that could only ever hide a defect.

**Current Pattern (Audited Code):**
```python
framework_map: dict[str, tuple] = {
    "ekman": (EkmanFACSFramework, "Ekman FACS"),
    "fbi": (FBIBAUFramework, "FBI BAU"),
    # Add other frameworks as they're implemented
}
# -> navarro / color / facellava silently skipped
```

**Target Pattern (Surgical Blueprint):**
```python
framework_map: dict[str, tuple] = {
    "ekman": (EkmanFACSFramework, "Ekman FACS"),
    "fbi": (FBIBAUFramework, "FBI BAU"),
    "navarro": (NavarroBodyLanguageFramework, "Navarro Body Language"),
    "color": (ColorPsychologyFramework, "Color Psychology"),
    "facellava": (FaceLLaVAFramework, "FaceLLaVA"),
}
# every framework now exposes get_for_analysis_type() / estimate_tokens()
```

### Refactor [R3]: Ad-Hoc Truncation → Explicit Report Contract (Finite Structure, Not Free Text)

- **Target Scope:** `src/prompts/builders/vision_builder.py:190-216` (pre-fix)
- **Engineering ROI:** Converts a 3-item request ("the model returns 3 items") into a 9-section contract with an explicit *never omit* rule — the difference between a thin summary and a forensic report.

**Current Pattern (Audited Code):**
```python
base_instructions = """
## ANALYSIS INSTRUCTIONS
Analyze the provided image focusing on observable, evidence-based indicators.

### Output Structure:
1. **Subject Identification**: ...
2. **Primary Analysis**: ...
3. **Confidence & Limitations**: ...
"""
```

**Target Pattern (Surgical Blueprint):**
```python
full_structure = """
## OUTPUT STRUCTURE (follow exactly, in this order)
1. **SUBJECT IDENTIFICATION** ...
2. **FACIAL ATTRIBUTES** (FaceLLaVA) ...
3. **FACIAL EXPRESSION ANALYSIS** (Ekman FACS) ...
4. **EYE ANALYSIS** ...
5. **BODY LANGUAGE ANALYSIS** (Navarro) ...
6. **CLOTHING & PRESENTATION** ...
7. **ENVIRONMENTAL CONTEXT** ...
8. **BEHAVIORAL PROFILE SUMMARY** (FBI BAU) ...
9. **CONFIDENCE & LIMITATIONS** ...

Rules:
- Never omit a section. If a cue is not visible, write "not visible in image".
- Support every claim with the specific cue that justifies it.
- Use calibrated language ("suggests", "consistent with"), never "proves".
"""
```

### Refactor [R4]: Two Sources, One Data Set — Merged, De-duplicated, Measured

- **Target Scope:** `src/agents/hannibal_agent.py:190-201, 267-284` (pre-fix)
- **Engineering ROI:** The report now uses *every* message available (buffer + persisted memory) instead of 24 hours of buffer only, and quotes locally measured statistics instead of model-invented ones.

**Current Pattern (Audited Code):**
```python
messages = message_buffer_service.get_recent_messages(chat_id, limit=200)
if target_user_id and target_user_id != "all":
    messages = [m for m in messages if m.user_id == target_user_id]
# -> "me" in text / "all" in text substring matching
# -> no persisted history, no statistics, no timestamps
```

**Target Pattern (Surgical Blueprint):**
```python
messages = await self._collect_messages(chat_id, target_user_id)   # buffer + memory, de-duplicated
stats = self._compute_stats(messages)                              # measured, not guessed
prompt = self._build_analysis_prompt(messages, target_user_id)     # statistics + verbatim messages
```

---

## 5. Phased Execution Roadmap & Scoped Agent Prompts

All phases below were **executed** in this session; the tree is green (`1038 passed, 1 skipped`) and `ruff check` / `ruff format --check` are clean.

1. **Phase 1 — Containment & Safety Lock (`P0` fixes + MVTH baseline tests)** — *done*
   - `hannibal_agent.py`: deliver every part; pin the group target to the requester.
   - `profiler_service.py` + `profiler_agent.py`: stop truncating; always deliver.
   - `utils/text_split.py`: one shared, invariant-preserving splitter.
2. **Phase 2 — Frame-Budget, Concurrency & State Hardening (`P1` fixes)** — *done*
   - `max_tokens` 4000 → 8000; buffer argument order + double-write guard; image-analyser truncation; reply-token-independent delivery; five-framework registry; missing trigger; word-boundary matching; text-provider registration gate; `.md` framework loader.
3. **Phase 3 — Structural De-Vibing & Modular Extraction (`P2/P3` refactors)** — *done*
   - Mandatory 9-section report contract; token-estimate de-duplication; timestamp normalisation; orphaned helper removal; `CHANGELOG.md`, `docs/HANNIBAL_PROFILE.md`, `docs/PROFILER_USAGE.md` synchronised.

### Copy-Paste Surgical Prompts for Coding Agents

> **Prompt [P0-1] (`src/agents/hannibal_agent.py`):**
> "Strictly scope edits to `src/agents/hannibal_agent.py` and `src/utils/text_split.py`. Replace the `_send_multipart_response` behaviour that sends only the first part with a delivery that replies part 1 and pushes every remaining part, so the full report reaches the user. Add a regression test asserting `push_message.call_count == len(parts) - 1` and that the concatenation of all sent messages contains the last section of the source report, then run the test suite to confirm green."

> **Prompt [P0-2] (`src/agents/hannibal_agent.py`):**
> "Strictly scope edits to `src/agents/hannibal_agent.py`. Add a trust-boundary guard so that in a group or room the analysis target is pinned to the requesting user's id (never 'all'), and so loose triggers such as 'read chat' are ignored in groups. Add a test asserting that a group profile's prompt contains no other member's messages."

> **Prompt [P1-1] (`src/agents/calendar_agent.py`, `src/services/message_buffer_service.py`):**
> "Strictly scope edits to `src/agents/calendar_agent.py` and `src/services/message_buffer_service.py`. Fix the `store_message(chat_id, user_id, text)` call to `store_message(chat_id=chat_id, text=text, user_id=user_id)`, and make `store_message` drop an identical `(text, user_id)` pair recorded within 5 seconds while preserving genuine repeats. Add tests for the swapped-argument regression, the double-write case, and the same-text-different-user case."

> **Prompt [P1-2] (`src/prompts/builders/vision_builder.py`, `src/prompts/frameworks/*.py`):**
> "Strictly scope edits to `src/prompts/builders/vision_builder.py` and `src/prompts/frameworks/`. Give `NavarroBodyLanguageFramework`, `ColorPsychologyFramework` and `FaceLLaVAFramework` the same `get_for_analysis_type`/`estimate_tokens` interface as `EkmanFACSFramework`, register all five frameworks in `framework_map`, and add a mandatory nine-section output structure to the instructions so the report is never summarised away. Update `tests/test_prompt_optimization.py` to assert every framework and the output structure are present."

---

## 6. Verification Evidence

| Check | Result |
| :--- | :--- |
| `pytest tests/ -q` | **1044 passed, 1 skipped** (pre-change baseline: 976 passed) |
| `ruff check src tests` | **All checks passed** |
| `ruff format --check src tests` | **249 files already formatted** |
| **Real mutation campaign** | 35 real source mutants applied to a scratch copy → **33 killed (94.3 %)**, 2 survivors **proven equivalent** by brute-force equivalence proof |
| Boot smoke (real FastAPI lifespan) | 12 agents registered; `HannibalProfileAgent` (6) and `ProfilerAgent` (7) both outrank `LLMAgent` (9) |
| Feature smoke — profiler | 17,040-char analysis → **5 parts delivered, 0 chars lost**, max part 3,727 chars, `"SECTION 13"` present, no `"[Analysis truncated]"` |
| Feature smoke — Hannibal | 120 messages → statistics block injected (120 msgs, 1 participant, 25 % questions, peak 09:00, median gap 1.0 min); report delivered in **3 messages, 0 chars lost** |
| Tree integrity (preflight telemetry) | `f14798eb96069295` (audit phase, zero mutation) → `565587d74b856b5e` (post-remediation) |

## 7. Known Limitations & Residual Risk (not fixed, deliberately)

| Item | Status | Why |
| :--- | :--- | :--- |
| **No live-model verification** | Not possible here | This environment has no API keys (no `.env`; `gemini_api_key`, `openrouter_api_key`, `hermes_api_key`, `nous_api_key` all unset). The prompt contract, token budget and delivery path are verified offline; the *model's* adherence to the 9-section contract is **not** verified against a real provider. Recommended: one live run per depth after deploy. |
| **`profiler_model` config field is dead** | Reported, not changed | The agent deliberately passes `model=None` (provider default) — pinning it would break Gemini. Changing the default could surprise an operator with an existing `.env`. |
| **Per-user rate limiting is inert** | Reported, not changed | `RateLimiter._is_user_in_secrets_group()` returns `False` unconditionally, so the advertised per-user limits never apply; both limits are chat-scoped. Enabling them changes global behaviour and needs a decision on what the "secrets group" is. |
| **Profiler session is keyed by chat** | Reported, not changed | In a group, a second member's trigger overwrites the first member's 60-second session, so the first member's image is then rejected by the user-match check. Fixing it needs a per-user session key, which changes the session manager's public API. |
| **God files remain** | Reported, not changed | `admin_agent.py` (2,108 LOC), `image_analyzer_agent.py` (1,456), `main.py` (1,274), `config.py` (1,024) are still far above the 400-LOC threshold. They were reviewed for the defect classes in scope, but a structural split is a separate, larger piece of work with real regression risk. |
| **LINE monthly quota** | Documented | A multi-part report costs one LINE message per part. Documented in `docs/PROFILER_USAGE.md` and `docs/HANNIBAL_PROFILE.md`. |

### Files changed (22 modified, 3 added)

```
M  CHANGELOG.md                                     M  src/agents/profiler_agent.py
M  docs/HANNIBAL_PROFILE.md                         M  src/config.py
M  docs/PROFILER_USAGE.md                           M  src/main.py
M  src/agents/calendar_agent.py                     M  src/prompts/builders/vision_builder.py
M  src/agents/hannibal_agent.py                     M  src/prompts/frameworks/color_psychology.py
M  src/agents/image_analyzer_agent.py               M  src/prompts/frameworks/facellava.py
M  src/services/conversation_memory_service.py      M  src/prompts/frameworks/navarro.py
M  src/services/message_buffer_service.py           M  src/services/profiler/framework_loader.py
M  src/services/profiler_service.py                 M  tests/test_calendar_scrape.py
M  tests/test_profiler_agent.py                     M  tests/test_prompt_optimization.py
A  src/utils/text_split.py                          A  tests/test_hannibal_agent.py
A  tests/utils/test_text_split.py
```
