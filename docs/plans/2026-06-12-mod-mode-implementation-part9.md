### Task 9: Wire ModModeAgent into AgentRouter (main.py)

**Objective:** Register ModModeAgent with all dependencies at startup.

**Files:**
- Modify: `src/main.py` (lifespan, agent registration)

**Step 1: Write test for integration**

```python
# tests/integration/test_mod_mode_integration.py
import pytest
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_mod_mode_agent_registered():
    from src.main import agent_router
    agents = agent_router.list_agents()
    mod_agent = next((a for a in agents if a["name"] == "ModModeAgent"), None)
    assert mod_agent is not None
    assert mod_agent["priority"] == 4
```

**Step 2: Run test (will fail before wiring)**

```bash
pytest tests/integration/test_mod_mode_integration.py -v
```

**Step 3: Update main.py lifespan**

Add to imports section:
```python
from src.agents.mod_mode_agent import ModModeAgent
from src.services.mod_mode_service import ModModeService
from src.services.ban_list_service import BanListService
from src.services.warning_service import WarningService
from src.services.harmful_content_detector import HarmfulContentDetector
from src.services.mod_audit_log import ModAuditLog
from src.agents.mod_mode.dashboard import ModDashboardBuilder
from src.services.convex_mod_repository import ConvexModRepository
```

Add to lifespan after HTTP client init:
```python
    # ========================================================================
    # PHASE: Moderator Mode Services Initialization
    # ========================================================================
    logger.info("🛡️ Initializing Moderator Mode services...")

    # Convex repository for mod tables
    convex_mod_repo = ConvexModRepository(convex_client)  # convex_client from calendar_service or new

    # Core services
    mod_mode_service = ModModeService(convex_mod_repo)
    ban_list_service = BanListService(convex_mod_repo)
    warning_service = WarningService(convex_mod_repo)
    harmful_detector = HarmfulContentDetector()  # Add LLM client if configured
    audit_log = ModAuditLog(
        token=settings.hf_memory_token,
        repo_id=settings.history_log_hf_repo_id or "evilevan/teacherboy-mod-audit",
    )
    dashboard_builder = ModDashboardBuilder()

    # Register ModModeAgent (Priority 4)
    mod_agent = ModModeAgent(
        mod_mode_service=mod_mode_service,
        ban_list_service=ban_list_service,
        warning_service=warning_service,
        harmful_detector=harmful_detector,
        audit_log=audit_log,
        dashboard_builder=dashboard_builder,
    )
    agent_router.register_agent(mod_agent)
    logger.info("🛡️ ModModeAgent registered (Priority 4)")
```

**Step 4: Run test to verify pass**

```bash
pytest tests/integration/test_mod_mode_integration.py -v
```

**Step 5: Commit**

```bash
git add src/main.py tests/integration/test_mod_mode_integration.py
git commit -m "feat(mod-mode): wire ModModeAgent into main.py"
```

---

### Task 10: Auto-Kick Banned Users on Rejoin

**Objective:** Extend member joined handler to auto-kick banned users.

**Files:**
- Modify: `src/handlers/message_handler.py` (handle_member_joined_event)

**Step 1: Write test**

```python
# tests/handlers/test_member_joined_mod.py
import pytest
from unittest.mock import AsyncMock, MagicMock

@pytest.mark.asyncio
async def test_auto_kick_banned_on_rejoin():
    from src.handlers.message_handler import handle_member_joined_event
    
    mock_event = MagicMock()
    mock_event.joined.members = [MagicMock(user_id="U999")]
    mock_event.source.type = "group"
    mock_event.source.group_id = "C123"
    
    mock_api = AsyncMock()
    
    with patch("src.handlers.message_handler.ban_list_service") as bls:
        bls.is_banned.return_value = True
        await handle_member_joined_event(mock_event, mock_api)
        mock_api.kick_users.assert_called_with("C123", ["U999"])
```

**Step 2: Run test to verify failure**

```bash
pytest tests/handlers/test_member_joined_mod.py -v
```

**Step 3: Update message_handler.py**

```python
# In handle_member_joined_event:
async def handle_member_joined_event(event, line_bot_api: MessagingApi):
    # ... existing code ...
    
    # Auto-kick banned users
    if event.source.type == "group":
        group_id = event.source.group_id
        from src.services.ban_list_service import ban_list_service
        for member in event.joined.members:
            user_id = member.user_id
            if await ban_list_service.is_banned(group_id, user_id):
                try:
                    await asyncio.to_thread(line_bot_api.kick_users, group_id, [user_id])
                    logger.info(f"👢 Auto-kicked banned user {user_id} on rejoin to {group_id}")
                except Exception as e:
                    logger.error(f"❌ Failed to auto-kick banned user: {e}")
```

**Step 4: Run test to verify pass**

```bash
pytest tests/handlers/test_member_joined_mod.py -v
```

**Step 5: Commit**

```bash
git add src/handlers/message_handler.py tests/handlers/test_member_joined_mod.py
git commit -m "feat(mod-mode): auto-kick banned users on rejoin"
```

---

### Task 11: Convex HTTP Endpoints for Mod Tables

**Objective:** Add Convex mutations/queries for the new tables.

**Files:**
- Create: `convex/modModeState.ts`, `convex/banList.ts`, `convex/userWarnings.ts`

**Implementation (TypeScript/Convex):**

```typescript
// convex/modModeState.ts
import { mutation, query } from "./_generated/server";
import { v } from "convex/values";

export const upsert = mutation({
  args: { groupId: v.string(), mode: v.union(v.literal("all"), v.literal("special")), activatedBy: v.string(), specialUserId: v.optional(v.string()), isActive: v.boolean() },
  handler: async (ctx, args) => {
    const existing = await ctx.db.query("modModeState").withIndex("by_group", q => q.eq("groupId", args.groupId)).unique();
    if (existing) {
      await ctx.db.patch(existing._id, { ...args, updatedAt: Date.now() });
      return { ...existing, ...args, updatedAt: Date.now() };
    }
    const id = await ctx.db.insert("modModeState", { ...args, createdAt: Date.now(), updatedAt: Date.now() });
    return { _id: id, ...args };
  },
});

export const getByGroup = query({
  args: { groupId: v.string() },
  handler: async (ctx, args) => ctx.db.query("modModeState").withIndex("by_group", q => q.eq("groupId", args.groupId)).unique(),
});

export const deactivate = mutation({
  args: { groupId: v.string() },
  handler: async (ctx, args) => {
    const doc = await ctx.db.query("modModeState").withIndex("by_group", q => q.eq("groupId", args.groupId)).unique();
    if (doc) await ctx.db.patch(doc._id, { isActive: false, updatedAt: Date.now() });
    return { success: true };
  },
});
```

```typescript
// convex/banList.ts
import { mutation, query } from "./_generated/server";
import { v } from "convex/values";

export const upsert = mutation({
  args: { groupId: v.string(), userId: v.string(), bannedBy: v.string(), reason: v.optional(v.string()), bannedAt: v.number() },
  handler: async (ctx, args) => {
    const existing = await ctx.db.query("banList").withIndex("by_group_user", q => q.eq("groupId", args.groupId).eq("userId", args.userId)).unique();
    if (existing) await ctx.db.patch(existing._id, args);
    else await ctx.db.insert("banList", args);
    return args;
  },
});

export const getByGroupUser = query({
  args: { groupId: v.string(), userId: v.string() },
  handler: async (ctx, args) => ctx.db.query("banList").withIndex("by_group_user", q => q.eq("groupId", args.groupId).eq("userId", args.userId)).unique(),
});

export const getByGroup = query({
  args: { groupId: v.string() },
  handler: async (ctx, args) => ctx.db.query("banList").withIndex("by_group", q => q.eq("groupId", args.groupId)).collect(),
});

export const remove = mutation({
  args: { groupId: v.string(), userId: v.string() },
  handler: async (ctx, args) => {
    const doc = await ctx.db.query("banList").withIndex("by_group_user", q => q.eq("groupId", args.groupId).eq("userId", args.userId)).unique();
    if (doc) await ctx.db.delete(doc._id);
    return { success: true };
  },
});
```

```typescript
// convex/userWarnings.ts
import { mutation, query } from "./_generated/server";
import { v } from "convex/values";

export const upsert = mutation({
  args: { groupId: v.string(), userId: v.string(), count: v.number(), lastWarningAt: v.number(), lastWarningBy: v.string(), lastWarningReason: v.optional(v.string()), readByUser: v.boolean(), readAt: v.optional(v.number()) },
  handler: async (ctx, args) => {
    const existing = await ctx.db.query("userWarnings").withIndex("by_group_user", q => q.eq("groupId", args.groupId).eq("userId", args.userId)).unique();
    if (existing) await ctx.db.patch(existing._id, { ...args, updatedAt: Date.now() });
    else await ctx.db.insert("userWarnings", { ...args, createdAt: Date.now(), updatedAt: Date.now() });
    return args;
  },
});

export const getByGroupUser = query({ ... });
export const getByGroup = query({ ... });
```

**Step: Deploy Convex schema + functions**

```bash
npx convex deploy
```

**Step: Commit**

```bash
git add convex/modModeState.ts convex/banList.ts convex/userWarnings.ts
git commit -m "feat(mod-mode): add Convex endpoints for mod tables"
```