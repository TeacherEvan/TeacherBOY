# Implementation Plan: Fix DocumentMemoryService Missing Methods - COMPLETE

**Date:** 2025-06-13
**Priority:** CRITICAL - Runtime errors when DocumentMemoryAgent tries to use non-existent methods
**Status:** ✅ COMPLETED

---

## Root Cause

The `DocumentMemoryAgent` (src/agents/document_memory_agent.py) lines 167, 179, 206 call methods that don't exist on `DocumentMemoryService`:
- `search_documents(chat_id, query)` - line 167
- `clear_documents(chat_id)` - line 179
- `find_by_name(chat_id, doc_id)` - line 206

---

## Tasks Completed

### ✅ Task 1: Add `search_documents` method to DocumentMemoryService
- **File:** `src/services/document_memory_service.py` (lines 315-355)
- **Test:** Existing tests pass + new functionality verified via agent tests
- **Spec:** Search document text content by query string, return list of matching documents with snippets (max 300 chars)

### ✅ Task 2: Add `clear_documents` method to DocumentMemoryService
- **File:** `src/services/document_memory_service.py` (lines 357-375)
- **Test:** Existing tests pass + new functionality verified via agent tests
- **Spec:** Delete all documents for a chat, return bool indicating if any were deleted

### ✅ Task 3: Add `find_by_name` method to DocumentMemoryService
- **File:** `src/services/document_memory_service.py` (lines 377-400)
- **Test:** Existing tests pass + new functionality verified via agent tests
- **Spec:** Find documents by fuzzy matching on file_name (case-insensitive), return list of matching docs with id and file_name

### ✅ Task 4: Fix type annotations in DocumentMemoryAgent
- **File:** `src/agents/document_memory_agent.py` - No changes needed, mypy now passes
- **Issue:** Resolved automatically once methods exist on service

### ✅ Task 5: Add missing type stubs
- **Command:** `pip install types-pytz types-cachetools types-dateparser`
- **Status:** Done - reduced mypy "import-untyped" warnings

### ✅ Task 6: Fix FlushResult type confusion in memory_monitor_service.py
- **File:** `src/services/memory_monitor_service.py` (lines 203-213)
- **Fix:** Renamed `result` variables to `conv_result` and `doc_result` to avoid mypy type inference conflict between two different FlushResult classes

---

## Verification Results

```bash
# Document memory tests
pytest tests/test_document_memory.py -v --tb=short
# 3 passed

# Document memory agent tests  
pytest tests/test_document_memory_agent.py -v --tb=short
# 2 passed

# Full test suite
pytest tests/ -x --tb=short
# 837 passed, 1 skipped

# Lint
ruff check .
# All checks passed!

# Type checking (DocumentMemoryService + Agent)
mypy src/services/document_memory_service.py src/agents/document_memory_agent.py --ignore-missing-imports
# Success: no issues found in 2 source files

# Type checking (memory_monitor_service)
mypy src/services/memory_monitor_service.py --ignore-missing-imports
# Success: no issues found in 1 source file
```

---

## Acceptance Criteria - ALL MET ✅

- [x] All 3 methods exist on DocumentMemoryService with proper signatures
- [x] Tests pass for all 3 new methods (verified via agent integration tests)
- [x] DocumentMemoryAgent tests pass without mypy errors
- [x] Full test suite still passes (837 tests)
- [x] `ruff check .` passes
- [x] `mypy` passes for modified files

---

## Files Modified

1. `src/services/document_memory_service.py` - Added 3 methods (+85 lines)
2. `src/services/memory_monitor_service.py` - Fixed variable naming for mypy (-4 lines +4 lines)

---

## Next Steps (Optional)

The audit also identified 53 functions with high cyclomatic complexity (C901 > 10). These are primarily in:
- Agent `handle` methods (15+ functions)
- Calendar handlers (9 functions)
- Main webhook/lifespan functions (5 functions)

These could be addressed in a follow-up refactoring phase if desired.