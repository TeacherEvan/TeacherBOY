# Moderator Mode — Master Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.
> **Design Doc:** `docs/plans/2026-06-12-mod-mode-design.md`
> **Plan Parts:** 9 task files (Part 1-9)

**Goal:** Build a dedicated Moderator Mode agent (Priority 4) for LINE groups with kick/warn/ban, two modes (all/special), admin Flex dashboard, Convex state + HF audit logs.

---

## Task Summary

| # | Task | Files | Est. Time |
|---|------|-------|-----------|
| 1 | Convex Repository Classes | `src/services/convex_mod_repository.py` + test | 5 min |
| 2 | ModModeService (Business Logic) | `src/services/mod_mode_service.py` + test | 5 min |
| 3 | BanListService | `src/services/ban_list_service.py` + test | 5 min |
| 4 | WarningService (3-strike) | `src/services/warning_service.py` + test | 5 min |
| 5 | HarmfulContentDetector | `src/services/harmful_content_detector.py` + test | 5 min |
| 6 | ModAuditLog (HF Hub) | `src/services/mod_audit_log.py` + test | 5 min |
| 7 | ModDashboardBuilder (Flex UI) | `src/agents/mod_mode/dashboard.py` + test | 10 min |
| 8 | ModModeAgent (Priority 4) | `src/agents/mod_mode_agent.py` + test | 15 min |
| 9 | Wire in main.py + member_joined hook + Convex endpoints | `src/main.py`, `src/handlers/message_handler.py`, `convex/*.ts` | 15 min |

**Total: ~75 minutes**

---

## Execution Order

1. **Convex Schema** (already done in design phase) → Deploy first
2. **Tasks 1-6** — Service layer (independent, can parallelize)
3. **Task 7** — Dashboard (depends on service interfaces)
4. **Task 8** — Agent (depends on all services)
5. **Task 9** — Integration wiring

---

## Verification Commands

```bash
# Run all mod-mode tests
pytest tests/services/test_convex_mod_repository.py \
       tests/services/test_mod_mode_service.py \
       tests/services/test_ban_list_service.py \
       tests/services/test_warning_service.py \
       tests/services/test_harmful_content_detector.py \
       tests/services/test_mod_audit_log.py \
       tests/agents/mod_mode/test_dashboard.py \
       tests/agents/test_mod_mode_agent.py \
       tests/handlers/test_member_joined_mod.py \
       tests/integration/test_mod_mode_integration.py -v

# Expected: ALL PASS

# Quick integration check
python -c "from src.main import agent_router; print([a['name'] for a in agent_router.list_agents()])"
# Should include: ModModeAgent (priority 4)
```

---

## Convex Deployment (Prerequisite)

```bash
cd /home/ewaldt/Documents/VS/Other/Bot/TeacherBOY
npx convex deploy
# Verify tables exist: modModeState, banList, userWarnings
```

---

## Acceptance Criteria

- [ ] `activate mod mode` (plain text) activates per-group mod mode
- [ ] `/modmode all` enables harmful content monitoring (3-strike)
- [ ] `/modmode special @user` restricts chat to admin + that user
- [ ] Banned users auto-kicked on rejoin
- [ ] Admin dashboard (/modmode dashboard) shows Flex UI with action buttons
- [ ] All actions logged to HF audit trail (`mod_audit_*.jsonl`)
- [ ] Mod mode completely separate from Ms. Green features
- [ ] Priority 4 ensures interception before translation/LLM agents
- [ ] Non-admins cannot trigger mod commands
- [ ] Convex indexes support O(1) ban/warning lookups

---

## Next Step

Run the **subagent-driven-development** skill to execute tasks 1-9 sequentially with two-stage review.