# Moderator Mode – Feature Documentation

> **Status:** ✅ Implemented & Deployed  
> **Version:** 1.1  
> **Priority:** 4 (intercepts before all other agents)  
> **Last Updated:** 2026-06-13

---

## Overview

**Moderator Mode** is a dedicated group-management system for LINE groups, completely separate from Ms. Green's translation/assistant features. It provides admin-controlled moderation with:

- **Per-group activation** — independent state per group/room
- **Two operating modes** — `all` (open + harmful detection) vs `special` (restricted speakers)
- **3-strike warning system** — auto-ban after 3 warnings, reading warnings counts as strikes
- **Ban list with auto-kick** — banned users cannot rejoin
- **Admin Dashboard** — LINE Flex Message with quick-reply buttons
- **Audit trail** — every action logged to Hugging Face Hub (append-only JSONL)

---

## Activation

### Triggers
```
activate mod mode
```
- Case-insensitive, anywhere in message
- **Only works in groups/rooms** (not 1:1 DMs)
- **Only by admin** (user in `ADMIN_USER_IDS` or claimed via `/admin claim`)
- **Per-group independent** — each group has its own mod state

```
/modmode all
/modmode special @user
```
- Shortcut to activate and set mode in one step
- Same admin/group rules apply

### Activation Flow
1. Admin sends `activate mod mode`, `/modmode all`, or `/modmode special @user` in group
2. Bot creates `modModeState` record in Convex and records the chosen mode
3. ModModeAgent is now handling traffic for that group
4. Bot replies with confirmation plus the next step (`/modmode` for status)

### Activation & Mode Commands

---

## Operating Modes

### `/Modmode all` — Open with Protection
| Behavior | Details |
|----------|---------|
| **Who can speak** | All group members |
| **Harmful content** | Auto-detected → warning issued |
| **Warnings** | 3 strikes = auto-ban + kick |
| **Admin powers** | Manual kick/warn/ban always available |

> **Harmful detection:** Keyword list (EN/TH) + optional LLM classification for edge cases. Covers hate speech, harassment, explicit content, scams, violence, self-harm, illegal acts, spam.

### `/Modmode special @user` — Restricted Chat
| Behavior | Details |
|----------|---------|
| **Who can speak** | Only activating admin + mentioned `@user` |
| **Others** | Messages deleted + warning issued |
| **Warnings** | 3 strikes = auto-ban + kick |
| **Read tracking** | User must acknowledge warning (counts as strike) |
| **Special user leaves** | Mode stays `special`; only admin can speak until `/modmode special @newuser` |

---

## Commands (Admin Only, in Mod-Enabled Group)

| Command | Description |
|---------|-------------|
| `/modmode` | Show current mode + dashboard |
| `/modmode dashboard` | Open Flex dashboard (quick-reply buttons) |
| `/modmode all` | Switch to **ALL** mode |
| `/modmode special @user` | Switch to **SPECIAL** mode (mention target user) |
| `/modmode kick @user` | Kick user from group |
| `/modmode warn @user [reason]` | Issue manual warning |
| `/modmode ban @user [reason]` | Ban user (adds to ban list + kicks) |
| `/modmode unban @user` | Remove from ban list |
| `/modmode banlist` | Show all banned users in this group |
| `/modmode deactivate` | Disable moderator mode for this group |

> **Non-admins:** Commands silently ignored (no response)

> **Current implementation status:** these `/modmode` text commands are the current working implementation. The Flex dashboard actions are implemented below.

---

## Admin Dashboard (Flex Message)

> **Current implementation status:** dashboard layouts are defined in `ModDashboardBuilder`, and postback actions are documented, but sending the Flex Message from `ModModeAgent` is not fully implemented yet. Use the `/modmode` command handlers below as the working path for now.

Trigger: `/modmode dashboard` or `/modmode`

```
┌─────────────────────────────────┐
│  🛡️ MODERATOR MODE DASHBOARD    │
│  Group: [Group Name]            │
│  Mode: ALL / SPECIAL @user      │
│  Status: ACTIVE / INACTIVE      │
├─────────────────────────────────┤
│  [👢 Kick User]  [⚠️ Warn]       │
│  [🔨 Ban]        [📋 Ban List]  │
│  [⚙️ Settings]   [❌ Deactivate] │
└─────────────────────────────────┘
```

Each button → quick-reply action or sub-menu. No typing required.

---

## Postback Handlers (Dashboard Actions)

The dashboard uses LINE **postback events** for button interactions. Each button sends an `action` parameter that is handled by `src/main.py`:

| Action | Description | Sub-flow |
|--------|-------------|----------|
| `mod_dashboard` | Show main dashboard | — |
| `mod_banlist` | Show banned users list | Paginated (10 per page) |
| `mod_warnlist` | Show warned users + strike count | — |
| `mod_settings` | Show mode settings | `all` / `special @user` |
| `mod_deactivate` | Deactivate mod mode | Confirmation required |
| `mod_set_all` | Switch to ALL mode | — |
| `mod_set_special` | Switch to SPECIAL mode | Prompts for `@user` mention |
| `mod_kick` | Show user list to kick | → `mod_kick_confirm` |
| `mod_kick_confirm` | Execute kick | Removes from group |
| `mod_warn` | Show user list to warn | → `mod_warn_confirm` |
| `mod_warn_confirm` | Execute warning | 3-strike logic applies |
| `mod_ban` | Show user list to ban | → ban + auto-kick |
| `mod_unban` | Show user list to unban | Removes from ban list |
| `mod_cancel` | Cancel pending destructive action | — |

**Postback data format:**
```
action=<action>&group_id=<groupId>&target_user_id=<userId>&page=<pageNum>
```

> **Note:** All postback handlers are admin-only. Non-admin interactions are silently ignored.

---

## LINE Mention Parsing (Special Mode)

When activating `/modmode special @user`, the bot extracts the target user's LINE ID from the **message mention entity** (not from text regex):

- Uses `event.message.mention.mentionees[0].user_id` — accurate even if display name changes
- **Fallback:** If mention entity unavailable, falls back to `@(\w+)` regex on text
- This ensures `@user` mentions work reliably with LINE's native mention UX

---

## Warning System (3-Strike)

### Automatic Warnings
- Harmful content detected (`/modmode all`)
- Non-allowed user speaks (`/modmode special`)

### Manual Warnings
- `/modmode warn @user [reason]`

### Admin Warning Reset
- **Convex mutation:** `resetWarnings(groupId, userId)` — resets count to 0, clears read status, adds audit entry
- Called via admin dashboard or internal unban flow
- Does **not** remove ban list entry (use `/modmode unban` separately)

### Strike Progression
| Strike | Action |
|--------|--------|
| 1 | Warning Flex sent to group (mentions user), logged to HF |
| 2 | Second warning, logged |
| 3 | **Auto-ban** → added to ban list + kicked from group, logged |

### Read Tracking (Special Mode)
- Warning Flex includes "✅ Acknowledge" button
- User pressing it = warning **counts** as read (strike registered)
- User ignoring = warning still counts (prevents gaming)

---

## Ban List & Auto-Kick

### Ban List (per group)
Stored in Convex `banList` table:
- `groupId`, `userId`, `bannedBy`, `reason`, `bannedAt`

### Auto-Kick on Rejoin
When a banned user tries to rejoin:
1. `handle_member_joined_event` fires
2. Bot checks `banList(groupId, userId)`
3. If match → immediate kick via LINE API
4. Action logged to HF audit trail

### Unban
`/modmode unban @user` removes from ban list. User can then rejoin normally.

---

## Harmful Content Detection

### Keyword-Based (Primary)
- Multi-language: English + Thai
- Categories: hate, harassment, sexual, violence, self-harm, illegal, spam, scam
- Configurable keyword lists in `HarmfulContentDetector`

### LLM-Based (Optional Fallback)
- Used when keyword detection uncertain
- Calls LLM via fallback chain (Gemini first, then OpenRouter, Hermes, HF Inference, Ollama)
- Classification: `SAFE` | `HARMFUL` | `BORDERLINE`

### Threshold
- `HARMFUL` → warning issued
- `BORDERLINE` → logged, no action (admin review via audit log)

---

## Audit Trail (Hugging Face Hub)

**Repository:** `hf://datasets/<HF_MEMORY_REPO>/mod_audit/`

**Format:** Append-only JSONL, one file per day (`mod_audit_YYYY-MM-DD.jsonl`)

### Logged Events
| Event | Fields |
|-------|--------|
| `MODE_ACTIVATED` | groupId, adminId, mode, specialUserId |
| `MODE_CHANGED` | groupId, adminId, oldMode, newMode, specialUserId |
| `MODE_DEACTIVATED` | groupId, adminId |
| `USER_KICKED` | groupId, adminId, targetUserId, reason |
| `USER_WARNED` | groupId, adminId, targetUserId, reason, strikeCount, auto |
| `USER_BANNED` | groupId, adminId, targetUserId, reason |
| `USER_UNBANNED` | groupId, adminId, targetUserId |
| `AUTO_KICK_REJOIN` | groupId, targetUserId |
| `HARMFUL_DETECTED` | groupId, userId, text, classification, action |

### Querying
```bash
# View today's audit log
huggingface-cli download <HF_MEMORY_REPO> mod_audit/mod_audit_2026-06-12.jsonl --repo-type dataset

# Or via Python
from huggingface_hub import hf_hub_download
path = hf_hub_download(repo_id="...", filename="mod_audit/mod_audit_2026-06-12.jsonl", repo_type="dataset")
```

---

## Architecture

### Agent Priority
```
Priority 4: ModModeAgent ◄── Intercepts FIRST in mod-enabled groups
Priority 5: AdminAgent, HelpAgent
Priority 6+: Calendar, Profiler, etc.
Priority 9-15: LLM, Translation, News
```

### Components

| Component | File | Responsibility |
|-----------|------|----------------|
| **ModModeAgent** | `src/agents/mod_mode_agent.py` | Priority 4 agent; intercepts messages in mod groups; routes to sub-handlers |
| **ModModeService** | `src/services/mod_mode_service.py` | Convex CRUD for modModeState; activation/deactivation; mode queries |
| **BanListService** | `src/services/ban_list_service.py` | Convex CRUD for banList; auto-kick on join; unban |
| **WarningService** | `src/services/warning_service.py` | Convex CRUD for userWarnings; 3-strike logic; read tracking |
| **HarmfulContentDetector** | `src/services/harmful_content_detector.py` | Keyword + optional LLM detection for `/modmode all` |
| **ModDashboardBuilder** | `src/agents/mod_mode/dashboard.py` | LINE Flex Message with quick-reply buttons for admin control |
| **ModAuditLog** | `src/services/mod_audit_log.py` | Append-only JSONL to HF Hub: kicks, warns, bans, mode changes |
| **MemberJoined Hook** | `src/handlers/message_handler.py` | Auto-kick banned users on rejoin |

### Data Flow

```
Message in mod-enabled group
         │
         ▼
┌────────────────────────┐
│ ModModeAgent.handle()  │
└───────────┬────────────┘
            │
    ┌───────┴───────┐
    ▼               ▼
Check Ban List   Check Mode
    │               │
    ▼          ┌────┴────┐
  Banned?    "special"   "all"
    │           │           │
    ▼           ▼           ▼
  Kick      Allowed?    Detect Harmful
              │           │
              ▼           ▼
            Warn/Del    Harmful?
              │           │
              ▼           ▼
           Strike       Warn → Strike
              │           │
              ▼           ▼
          Count>=3?   Count>=3?
              │           │
              ▼           ▼
             Ban        Ban
              │           │
              └─────┬─────┘
                    ▼
             Log to HF Hub
                    │
                    ▼
          Return False (allow other agents)
```

---

## Convex Schema

```typescript
// Moderator Mode state per group
modModeState: defineTable({
  groupId: v.string(),
  mode: v.union(v.literal("all"), v.literal("special")),
  activatedBy: v.string(),
  specialUserId: v.optional(v.string()),
  isActive: v.boolean(),
  createdAt: v.number(),
  updatedAt: v.number(),
})
  .index("by_group", ["groupId"])
  .index("by_admin", ["activatedBy"])

// Ban list per group
banList: defineTable({
  groupId: v.string(),
  userId: v.string(),
  bannedBy: v.string(),
  reason: v.optional(v.string()),
  bannedAt: v.number(),
})
  .index("by_group_user", ["groupId", "userId"])
  .index("by_group", ["groupId"])

// User warnings per group (3-strike system)
userWarnings: defineTable({
  groupId: v.string(),
  userId: v.string(),
  count: v.number(),                      // 1, 2, 3 (3 = auto-ban)
  lastWarningAt: v.number(),
  lastWarningBy: v.string(),
  lastWarningReason: v.optional(v.string()),
  readByUser: v.boolean(),                // Has user acknowledged?
  readAt: v.optional(v.number()),
})
  .index("by_group_user", ["groupId", "userId"])
  .index("by_group", ["groupId"])

// Mutation: resetWarnings(groupId, userId) — admin unban path
// Resets count to 0, clears read status, adds audit entry
```

---

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Convex unavailable | Fail closed: deny message, log locally, alert admin |
| LINE kick API fails | Retry 3× with backoff; if failed, log + alert admin |
| HF audit log fails | Queue locally, retry on next write; **never blocks** mod action |
| Non-admin tries command | Silent ignore (no response) |
| Special user leaves group | Mode stays `special`; only admin can speak; admin can `/modmode special @newuser` |

---

## Testing

### Unit Tests (pytest)
```bash
pytest tests/services/test_mod_mode_service.py -v
pytest tests/services/test_ban_list_service.py -v
pytest tests/services/test_warning_service.py -v
pytest tests/services/test_harmful_content_detector.py -v
pytest tests/agents/mod_mode/test_dashboard.py -v
pytest tests/services/test_mod_audit_log.py -v
```

### Integration Tests
```bash
pytest tests/integration/test_mod_mode_integration.py -v
```

### Test Coverage
- ModModeService: CRUD + activation logic
- BanListService: ban/unban/auto-kick check
- WarningService: 3-strike, read tracking
- HarmfulContentDetector: keyword + LLM paths
- ModDashboardBuilder: Flex dict structure
- ModModeAgent: should_handle for various states
- Full message flow: banned user → kick
- Full message flow: special mode → non-allowed user warned
- Member joined → banned user auto-kick

---

## Deployment

### Prerequisites
1. **Convex schema migration** — deploy schema first, then code
2. **HF repo** — ensure `HF_MEMORY_TOKEN` has write access to audit repo
3. **Environment** — no new env vars required (uses existing HF/Convex config)

### Rollback
Disable ModModeAgent registration in `src/main.py` if issues:
```python
# In lifespan startup, comment out:
# mod_mode_agent = ModModeAgent(...)
# agent_router.register_agent(mod_mode_agent)
```

### Verification Checklist
- [ ] Admin can say `activate mod mode` in group → mode activated
- [ ] `/Modmode all` enables harmful-content detection with 3-strike
- [ ] `/Modmode special @user` restricts chat to admin + that user
- [ ] Banned users auto-kicked on rejoin
- [ ] Admin dashboard (Flex) works with quick-reply buttons
- [ ] All actions logged to HF audit trail
- [ ] Mod mode completely separate from Ms. Green features
- [ ] Priority 4 ensures interception before translation/LLM agents
- [ ] Non-admins cannot trigger mod commands
- [ ] Convex indexes support O(1) ban/warning lookups

---

## Related Documentation

- **Design:** `docs/plans/2026-06-12-mod-mode-design.md`
- **Implementation:** `docs/plans/2026-06-12-mod-mode-implementation.md` (parts 1-9)
- **Architecture:** `docs/architecture/agents.md` (Priority 4 entry)
- **Admin Commands:** `docs/ADMIN_COMMANDS.md` (separate AdminAgent commands)
- **Convex Schema:** `convex/schema.ts` (modModeState, banList, userWarnings)

---

## Quick Reference Card

| Action | Command |
|--------|---------|
| Activate | `activate mod mode` |
| Open dashboard | `/modmode` or `/modmode dashboard` |
| Open mode | `/modmode all` |
| Restricted mode | `/modmode special @user` |
| Kick user | `/modmode kick @user` |
| Warn user | `/modmode warn @user [reason]` |
| Ban user | `/modmode ban @user [reason]` |
| Unban user | `/modmode unban @user` |
| Show ban list | `/modmode banlist` |
| Deactivate | `/modmode deactivate` |

> **Only works in groups where mod mode is active. Only for admins.**