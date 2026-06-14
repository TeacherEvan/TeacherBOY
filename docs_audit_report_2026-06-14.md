# Documentation Audit Report - TeacherBOY / Ms. Green
**Date:** 2026-06-14  
**Scope:** `/home/ewaldt/Documents/VS/Other/Bot/TeacherBOY`  
**Auditor:** Hermes (documentation-maintenance skill)

---

## Executive Summary

**Health: GOOD** — Documentation is well-structured with clear entry point (`docs/README.md`), comprehensive feature docs, and healthy internal links. However, several issues need addressing before "definition of done" for recent features.

---

## Findings by Category

### 1. Legacy Naming (CRITICAL)

| File | Line | Issue | Recommendation |
|------|------|-------|----------------|
| `README.md` | 108-113, 210-213 | `ZEUS_GROUP_ACCESS_MODE`, `ZEUS_ALLOWED_GROUP_IDS`, `ZEUS_DENIED_GROUP_IDS` env vars and references | Rename to `MS_GREEN_GROUP_ACCESS_MODE` / `GREEN_ALLOWED_GROUP_IDS` / `GREEN_DENIED_GROUP_IDS`. Update `.env.example` and `config.py` |
| `README.md` | 111 | "Boss Easter Egg: If asked 'who is boss', replies with exactly: `Evan...`" | Update to reference Ms. Green persona |

**Status:** ⚠️ **Blocker for production confidence** — Legacy env var names in public README will confuse operators.

---

### 2. Stale Plan Files (HIGH)

| File | Age | Status | Action |
|------|-----|--------|--------|
| `docs/plans/2025-06-13-fix-document-memory-methods.md` | ~1 year | Completed | Archive → `docs/plans/.archive/` with status badge |
| `docs/plans/2026-06-07-ms-green-features-toggle-design.md` | 1 week | Completed? | Verify completion → Archive or mark Active |
| `docs/plans/2026-06-08-ms-green-features-design.md` | 6 days | Completed? | Verify completion → Archive or mark Active |
| `docs/plans/2026-06-14-modmode-command-handlers.md` | Today | **Active** | Keep in `plans/`, add 🔄 **Active** badge |

**Recommendation:** Adopt **Plan Archival Pattern** (from skill):
- Move completed plans to `docs/plans/.archive/`
- Add frontmatter badge: `**Status:** ✅ **Archived — Implemented & Verified**`
- Active plans get 🔄 **Active**, design specs get 🔄 **Design Complete**

---

### 3. Feature Documentation Drift (HIGH)

| Feature Doc | Missing Current Implementation |
|-------------|-------------------------------|
| `docs/IMAGE_ANALYZER.md` | • Quick Reply buttons flow (🔍 Analyze / 📝 Scrape / 📖 Generate Debrief)<br>• "M" shorthand for debrief mode<br>• New/Last choice flow for bare `analyze` trigger<br>• Priority 7 routing detail (same as Profiler) |
| `docs/CALENDAR_REMINDERS.md` | Not reviewed — verify against current CalendarAgent implementation |
| `docs/PROFILER_USAGE.md` | Not reviewed — verify against current ProfilerAgent implementation |
| `docs/reference/quick-reference.md` | Line 19: `git push --force-with-lease hf main:main` missing HF_TOKEN context (see `.hermes-instructions`) |

**Severity:** IMAGE_ANALYZER.md documents **old 3-step flow** but implementation has **5-step flow with Quick Replies**. Users/docs will be confused.

---

### 4. Entry Points & Discoverability (MEDIUM)

| Entry Point | Status | Issue |
|-------------|--------|-------|
| `docs/README.md` | ✅ Good | Clear hub, well-organized sections |
| Root `README.md` | ✅ Good but... | Duplicates some docs content; env var section has legacy ZEUS names |
| `AGENTS.md` | ✅ Good | Agent context for AI assistants |
| `docs/guides/quickstart.md` | ✅ Good | Mentions legacy "Zeus" as historical context (acceptable) |
| `.github/copilot-instructions.md` | Exists | Not reviewed for currency |

**Recommendation:** Keep root README focused on project identity + quickstart; point to `docs/README.md` for all feature docs.

---

### 5. Link Health (PASS)

| Target | Links Checked | Result |
|--------|---------------|--------|
| `docs/` | 75 | ✅ All resolve |
| `docs/README.md` | (internal) | ✅ All resolve |
| `README.md` | 0 (no markdown links) | N/A |
| `AGENTS.md` | 0 (no markdown links) | N/A |

**Note:** Script correctly resolves relative links from each file's directory.

---

### 6. Architecture Sync (PASS)

- `docs/architecture/overview.md` — Current (mentions ModModeAgent Priority 4, MetricsService provider latency)
- `docs/architecture/agents.md` — Current (full priority table with ModModeAgent at 4)
- `docs/reference/environment.md` — Comprehensive (283 lines, all current env vars)

---

### 7. Reference Completeness (MEDIUM)

| Area | Coverage | Gaps |
|------|----------|------|
| Environment variables | ✅ Complete (283 lines) | ZEUS_* legacy names in root README not in env reference |
| CLI commands | ✅ In ADMIN_COMMANDS.md, quick-reference.md | — |
| Agent priorities | ✅ In architecture/agents.md | — |
| Rate limits | ✅ In quick-reference.md table | Image Analyzer rate limit (5/hr) not in IMAGE_ANALYZER.md |
| Deployment | ⚠️ Partial | Root README has `git push hf` but missing HF_TOKEN requirement (see `.hermes-instructions`) |

---

### 8. Code-Doc Drift (HIGH)

| Feature | Implementation | Documentation | Drift |
|---------|----------------|---------------|-------|
| Image Analyzer | 5-step flow + Quick Replies + "M" shorthand | 3-step flow, no buttons | **Major** |
| Moderator Mode | ✅ Full impl + dashboard | ✅ Comprehensive MODERATOR_MODE.md | Minor (plan file exists) |
| Calendar | Not verified | CALENDAR_REMINDERS.md | Unknown |
| Profiler | Not verified | PROFILER_USAGE.md | Unknown |
| Deployment | Direct HF push required | Root README + guides/deployment.md | Missing billing context |

---

## Recommended Action Plan

### Immediate (Before Next Deploy)
1. **Fix legacy ZEUS env vars** in README.md → MS_GREEN_* / GREEN_*
2. **Update IMAGE_ANALYZER.md** to reflect current Quick Reply flow
3. **Archive completed plan files** to `docs/plans/.archive/`
4. **Update quick-reference.md** deployment line with HF_TOKEN context

### This Sprint
5. **Verify CALENDAR_REMINDERS.md** against CalendarAgent implementation
6. **Verify PROFILER_USAGE.md** against ProfilerAgent implementation
7. **Add Image Analyzer rate limit** (5/hr) to IMAGE_ANALYZER.md
8. **Create docs/plans/.archive/** and move 3 completed plans

### Ongoing
9. Add **"Definition of Done" checklist** to PR template: "Docs updated for changed features"
10. Run link verification pre-merge: `python scripts/verify_markdown_links.py docs/`

---

## File Inventory (for reference)

```
docs/
├── README.md                          # ✅ Hub - current
├── ADMIN_COMMANDS.md                  # ✅ Complete
├── ADMIN_QUICK_START.md               # ✅ Quick start
├── CALENDAR_REMINDERS.md              # ⚠️ Not verified
├── CONVERSATION_MEMORY.md             # ✅ Complete
├── DOCUMENT_MEMORY.md                 # ✅ Complete
├── GITHUB_MODELS.md                   # ✅ Complete
├── GOOGLE_CALENDAR.md                 # ✅ Complete
├── HANNIBAL_PROFILE.md                # ✅ Complete
├── IMAGE_ANALYZER.md                  # ❌ OUTDATED (major drift)
├── IMAGE_PRIVACY.md                   # ✅ Complete
├── INCOMPLETE_SENTENCE_FIX.md         # ✅ Complete
├── KPS_ASSISTANT.md                   # ✅ Complete
├── MODERATOR_MODE.md                  # ✅ Comprehensive
├── NEWS_AGENT.md                      # ✅ Complete
├── NEWS_USAGE_EXAMPLES.md             # ✅ Complete
├── PROFILER_USAGE.md                  # ⚠️ Not verified
├── SEARCH_AGENT.md                    # ✅ Complete
├── TRACING.md                         # ✅ Complete
├── architecture/
│   ├── overview.md                    # ✅ Current
│   └── agents.md                      # ✅ Current
├── guides/
│   ├── quickstart.md                  # ✅ Good
│   ├── line-setup.md                  # (exist)
│   ├── deployment.md                  # (exist)
│   └── PRODUCTIVITY_OPTIMIZATIONS.md  # ✅ Complete
├── plans/
│   ├── 2025-06-13-fix-document-memory-methods.md      # 📦 Archive
│   ├── 2026-06-07-ms-green-features-toggle-design.md  # 📦 Archive?
│   ├── 2026-06-08-ms-green-features-design.md         # 📦 Archive?
│   └── 2026-06-14-modmode-command-handlers.md         # 🔄 Active
├── reference/
│   ├── environment.md                 # ✅ Complete
│   ├── quick-reference.md             # ⚠️ Minor (deploy line)
│   └── maintainers.md                 # (exist)
├── superpowers/                       # (implementation plans)
└── audit/                             # (previous audits)
```

---

## Verification Commands

```bash
# Link verification
python /home/ewaldt/.hermes/skills/software-development/documentation-maintenance/scripts/verify_markdown_links.py docs/

# Legacy name scan
grep -r "ZEUS" docs/ --include="*.md" | grep -v "Legacy" | grep -v "AUDIT"

# Plan file status
ls -la docs/plans/
```

---

**Next Audit:** After Image Analyzer docs update + plan archival