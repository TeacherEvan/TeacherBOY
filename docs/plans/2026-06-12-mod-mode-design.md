# Moderator Mode — Design Document

> **Status:** APPROVED — Ready for Writing Plans phase
> **Date:** 2026-06-12
> **Approach:** Dedicated ModModeAgent (Priority 4) with Convex state + HF audit logs

---

## 1. Architecture Overview

Moderator Mode is a **separate, high-priority agent** that intercepts ALL messages in groups where mod mode is activated. It operates independently of Ms. Green's translation/assistant features.

```
┌─────────────────────────────────────────────────────────────────┐
│                        Agent Router                              │
│  Priority 4: ModModeAgent ◄── Intercepts FIRST in mod groups   │
│  Priority 5: AdminAgent, HelpAgent                               │
│  Priority 6+: Calendar, Profiler, etc.                          │
│  Priority 9-15: LLM, Translation, News                          │
└─────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│                      ModModeAgent                                │
│  • should_handle() → true if group has mod mode active         │
│  • handle() → routes to:                                        │
│      - Activation commands ("activate mod mode")                │
│      - Admin commands (/modmode, kick, warn, ban, dashboard)   │
│      - Message filtering (block non-allowed users in special)  │
│      - Auto-detection (harmful content in /modmode all)        │
└─────────────────────────────────────────────────────────────────┘
         │
    ┌────┴────┐
    ▼         ▼
Convex      HF Hub
State       Audit Logs
```

---

## 2. Convex Schema Additions

Add to `convex/schema.ts`:

```typescript
// Moderator Mode state per group
modModeState: defineTable({
  groupId: v.string(),                    // LINE group/room ID
  mode: v.union(v.literal("all"), v.literal("special")),  // "all" | "special"
  activatedBy: v.string(),                // LINE user ID of activating admin
  specialUserId: v.optional(v.string()),  // Only for mode="special"
  isActive: v.boolean(),                  // Quick enable/disable
  createdAt: v.number(),
  updatedAt: v.number(),
})
  .index("by_group", ["groupId"])
  .index("by_admin", ["activatedBy"])

// Ban list per group
banList: defineTable({
  groupId: v.string(),
  userId: v.string(),                     // Banned user's LINE ID
  bannedBy: v.string(),                   // Admin who banned
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
  lastWarningBy: v.string(),              // Admin who warned
  lastWarningReason: v.optional(v.string()),
  // For "read warning counts" — track if user has seen warning
  readByUser: v.boolean(),                // Has user acknowledged?
  readAt: v.optional(v.number()),
})
  .index("by_group_user", ["groupId", "userId"])
  .index("by_group", ["groupId"])
```

---

## 3. Components and Responsibilities

| Component | File | Responsibility |
|-----------|------|----------------|
| **ModModeAgent** | `src/agents/mod_mode_agent.py` | Priority 4 agent; intercepts messages in mod groups; routes to sub-handlers |
| **ModModeService** | `src/services/mod_mode_service.py` | Convex CRUD for modModeState; activation/deactivation; mode queries |
| **BanListService** | `src/services/ban_list_service.py` | Convex CRUD for banList; auto-kick on join; unban |
| **WarningService** | `src/services/warning_service.py` | Convex CRUD for userWarnings; 3-strike logic; read tracking |
| **HarmfulContentDetector** | `src/services/harmful_content_detector.py` | Keyword + optional LLM detection for `/modmode all` |
| **ModDashboardBuilder** | `src/agents/mod_mode/dashboard.py` | LINE Flex Message with quick-reply buttons for admin control |
| **HF Audit Logger** | `src/services/mod_audit_log.py` | Append-only JSONL to HF Hub: kicks, warns, bans, mode changes |
| **MemberJoined Hook** | Extend `handle_member_joined_event` | Auto-kick banned users on rejoin |

---

## 4. Activation & Commands

### Activation Trigger
- **Plain text:** `activate mod mode` (case-insensitive, anywhere in message)
- **Only works in groups/rooms** (not 1:1)
- **Only by admin** (ADMIN_USER_IDS or claimed admin)
- **Per-group independent** — each group has its own mod state

### Mode Commands (admin only, in mod-enabled group)

#### `/Modmode all`
- All users can speak
- Harmful content → auto-warn (3 strikes = auto-ban)
- Admins can still manual kick/warn/ban

#### `/Modmode special @user`
- Only activating admin + mentioned user can speak
- All other users' messages are silently deleted (or warned)
- 3 warnings per user (reading warning counts)
- After 3 warnings → auto-ban

### Admin Dashboard (Flex Message)
Triggered by `/modmode dashboard` or `/modmode` alone:

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

Each button → quick-reply action or sub-menu.

---

## 5. Data Flow

### Message Interception (ModModeAgent.handle)
```
1. Event received in group with active mod mode
2. Extract user_id, group_id, text
3. Check banList(group_id, user_id) → if banned: kick + return
4. Check mode:
   - "special": if user_id not in {activating_admin, special_user} → warn/delete
   - "all": run harmfulContentDetector(text) → if harmful: warn
5. If warning issued:
   - Increment warning count
   - If count >= 3 → ban + kick
   - Send warning Flex to group (mentions user)
   - Log to HF audit
6. If message allowed → return False (let other agents process)
```

### Auto-Kick on Rejoin
```
handle_member_joined_event:
  For each joined member:
    If banList(group_id, user_id) exists:
      Kick user via LINE API
      Log to HF audit
```

---

## 6. Error Handling

| Scenario | Behavior |
|----------|----------|
| Convex unavailable | Fail closed: deny message, log locally, alert admin |
| LINE kick API fails | Retry 3x with backoff; if failed, log + alert admin |
| HF audit log fails | Queue locally, retry on next write; never block mod action |
| Non-admin tries command | Silent ignore (no response) |
| Special user leaves group | Mode stays "special" but only admin can speak; admin can `/modmode special @newuser` |

---

## 7. Testing Strategy

### Unit Tests (pytest)
- `ModModeService`: CRUD + activation logic
- `BanListService`: ban/unban/auto-kick check
- `WarningService`: 3-strike, read tracking
- `HarmfulContentDetector`: keyword + LLM paths
- `ModDashboardBuilder`: Flex dict structure

### Integration Tests
- ModModeAgent.should_handle() for various states
- Full message flow: banned user → kick
- Full message flow: special mode → non-allowed user warned
- Member joined → banned user auto-kick

### Fixtures
- Mock Convex client
- Mock LINE MessagingApi
- Sample group/user IDs

---

## 8. Deployment Notes

1. **Convex schema migration**: Deploy schema first, then code
2. **HF repo**: Ensure `hf_memory_token` has write access to audit repo
3. **Environment**: No new env vars required (uses existing HF/Convex config)
4. **Rollback**: Disable ModModeAgent registration in `main.py` if issues

---

## 9. Acceptance Criteria

- [ ] Admin can say "activate mod mode" in group → mode activated
- [ ] `/Modmode all` enables harmful-content detection with 3-strike
- [ ] `/Modmode special @user` restricts chat to admin + that user
- [ ] Banned users auto-kicked on rejoin
- [ ] Admin dashboard (Flex) works with quick-reply buttons
- [ ] All actions logged to HF audit trail
- [ ] Mod mode completely separate from Ms. Green features
- [ ] Priority 4 ensures interception before translation/LLM agents
- [ ] Non-admins cannot trigger mod commands
- [ ] Convex indexes support O(1) ban/warning lookups