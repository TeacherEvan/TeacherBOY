# Code Quality Cleanup Plan

**Date:** 2026-06-07
**Branch:** fix/translation-provider-chain (or new cleanup branch)
**Base Commit:** Current HEAD

## Objective
Fix all linting, formatting, type-checking, and test failures identified in the full codebase audit.

## Tasks

### Batch 1: Linting & Formatting (Auto-fixable)
- [ ] Task 1.1: Run `ruff check --fix .` to fix 74 auto-fixable lint issues
- [ ] Task 1.2: Run `ruff format .` to fix 15 formatting issues
- [ ] Task 1.3: Verify no regressions: `ruff check .` and `ruff format --check .`

### Batch 2: Type Checking Dependencies
- [ ] Task 2.1: Install missing mypy stubs: `types-python-dateutil types-cachetools types-dateparser types-pytz`
- [ ] Task 2.2: Run mypy to verify reduction in errors
- [ ] Task 2.3: Fix `scripts/convex_backfill.py` module naming conflict (add `__init__.py` or adjust)

### Batch 3: Test Failures Investigation
- [ ] Task 3.1: Run failing tests individually to capture error details
- [ ] Task 3.2: Analyze root cause of each failure (6 tests)
- [ ] Task 3.3: Fix failing tests or implementation code
- [ ] Task 3.4: Run full test suite to confirm all pass

### Batch 4: Final Verification
- [ ] Task 4.1: Run complete verification pipeline: pytest, ruff check, ruff format, mypy
- [ ] Task 4.2: Capture evidence output for each
- [ ] Task 4.3: Commit changes with descriptive message

## Success Criteria
- [ ] `ruff check .` → 0 errors
- [ ] `ruff format --check .` → "All files formatted"
- [ ] `mypy . --ignore-missing-imports` → 0 errors (or only import-untyped for external deps)
- [ ] `pytest` → All tests pass (0 failed)
- [ ] No security issues in diff

## Notes
- Test failures likely related to recent translation/provider chain changes
- The `llm_fallback.py` ollama import removal was intentional (lazy import pattern)
- Keep changes minimal and focused on quality fixes only