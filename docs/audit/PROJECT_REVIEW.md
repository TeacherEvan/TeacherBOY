# Project Review Override: TeacherBOY / Ms. Green

**Project:** TeacherBOY (Ms. Green) - Multi-Agent LINE Translation Bot
**Language:** Python 3.11+, FastAPI, LINE Bot SDK v3
**Architecture:** Agent-based routing with service layer singletons initialized in lifespan

---

## Project-Specific Anti-Patterns (CRITICAL)

| Pattern | Severity | Fix |
|---------|----------|-----|
| Importing service module variable (`from src.services.x import y_service`) before lifespan init | CRITICAL | Use `from src.services.x import get_y_service` and call getter at runtime |
| Using stale module variable in registration/check logic after initialization | CRITICAL | Call `get_y_service()` at point of use, not at module import |
| Handler using optional service without null guard | HIGH | `if service is None: return` or `logger.debug("..."); return` early |

---

## Service Initialization Pattern

TeacherBOY uses **lazy-initialized singletons** via getter functions:

```python
# services/ban_list_service.py
ban_list_service: BanListService | None = None

def get_ban_list_service() -> BanListService | None:
    return ban_list_service

def init_ban_list_service(repo):
    global ban_list_service
    ban_list_service = BanListService(repo)
```

**Always use getter pattern:**
```python
# ✅ CORRECT - in handler/module
from src.services.ban_list_service import get_ban_list_service
ban_service = get_ban_list_service()
if ban_service is None:
    return
await ban_service.is_banned(...)

# ❌ WRONG - imports stale None at module load
from src.services.ban_list_service import ban_list_service
await ban_list_service.is_banned(...)  # AttributeError!
```

---

## Lifespan Initialization Order

Services are initialized in `src/main.py` lifespan **after** imports:
```python
# Top of main.py - imports module variables (all None at this point)
from src.services.ban_list_service import ban_list_service, init_ban_list_service

# Inside lifespan - after Convex client ready
init_ban_list_service(convex_mod_repo)  # Now ban_list_service is set

# Registration MUST use getter, not stale import:
from src.services.ban_list_service import get_ban_list_service
ban_list_svc = get_ban_list_service()
if ban_list_svc: ...
```

---

## Code Review Checklist Additions

When reviewing TeacherBOY code, verify:

- [ ] No `from src.services.* import *_service` (bare module variable) in handlers/utils
- [ ] All optional service usages have `if service is None: return` guard
- [ ] Registration logic in lifespan uses `get_*_service()` calls
- [ ] No direct module variable usage after initialization phase
- [ ] New services follow the getter pattern (`get_x_service()` + `init_x_service()`)

---

## Custom Search Patterns for TeacherBOY

```bash
# Find direct service module imports (bypasses getter)
rg "from src\.services\.\w+ import \w+_service\b" --type py

# Find direct module variable usages in handlers
rg "\b(mod_mode_service|ban_list_service|warning_service|conversation_memory_service|group_membership_service|metrics_service)\b" --type py src/handlers/ | rg -v "get_\w+_service"

# Find stale variable usage in registration logic
rg "\b(mod_mode_service|ban_list_service|warning_service)\b" --type py src/main.py | rg -v "get_\w+_service|init_\w+_service"
```

---

## Required Test Patterns

- Tests must mock Convex client and initialize services via `init_*_service()`
- Handler tests must verify null guards work (service returns None when not initialized)
- Integration tests must verify lifespan initialization order