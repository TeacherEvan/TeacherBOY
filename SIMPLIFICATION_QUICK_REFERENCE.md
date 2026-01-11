# 🚀 Simplification Quick Reference

**Last Updated:** January 11, 2026  
**Full Documentation:** [INTEGRATION_ECOSYSTEM_AUDIT.md](INTEGRATION_ECOSYSTEM_AUDIT.md)

---

## ⚡ The Five Principles (Non-Negotiable)

### 1️⃣ Single Responsibility

- **Agents:** ≤600 lines
- **Services:** ≤500 lines
- **Flows:** ≤400 lines
- **Fix:** Split into modules when limit exceeded

### 2️⃣ Lazy Loading

- Use `AgentFactory.register()` for agents
- Use `@property` getters for flows
- Load data files on first use, not import
- **Test:** Startup <200ms, <150MB memory

### 3️⃣ Dependency Injection

- Services injected via `__init__`, NOT imported directly
- No circular dependencies
- Testable in isolation
- **Pattern:** `def __init__(self, service: ServiceType)`

### 4️⃣ Backward Compatibility

- Public APIs unchanged or deprecated (2 releases)
- Database migrations for schema changes
- Test coverage ≥94%
- Feature flags for big changes

### 5️⃣ Observable Simplification

- Track metrics: lines, coverage, performance
- Weekly automated reports
- PR descriptions include before/after
- Quarterly roadmap reviews

---

## 🚫 Anti-Patterns (Auto-Reject)

| Anti-Pattern      | Example                 | Fix                   |
| ----------------- | ----------------------- | --------------------- |
| God Classes       | 1,597-line agent        | Split into flows      |
| Copy-Paste        | Friend check in 3 files | Extract to service    |
| Eager Loading     | Load at import          | Lazy load on use      |
| Hidden Deps       | Direct service import   | Inject via `__init__` |
| Circular Deps     | A→B→A                   | Use TYPE_CHECKING     |
| Magic Numbers     | `if len > 500:`         | Define constant       |
| Untestable        | Tight coupling          | Dependency injection  |
| No Error Handling | Bare API calls          | try-except + fallback |

---

## ✅ Pre-Commit Checklist

Before creating a PR:

- [ ] File sizes within limits (agents ≤600, services ≤500)
- [ ] Services injected, not imported
- [ ] Lazy loading for new flows/agents
- [ ] Tests pass: `pytest --cov=src`
- [ ] Coverage ≥94%
- [ ] Performance benchmark: `python scripts/measure_startup.py`
- [ ] Update docs if architecture changed

---

## 📈 Priority Refactoring Targets

### Phase 1: High-Impact Quick Wins (Weeks 1-4)

1. **AdminAgent** (1,597 lines) → 400 lines + 5 modules
2. **ImageAnalyzerAgent** (1,041 lines) → 350 lines + 4 modules
3. **BaseSessionManager** (consolidate 6 managers)

### Phase 2: Service Layer (Weeks 5-8)

4. **Service Registry** implementation
5. **LLM Provider Abstraction**
6. **Translation Service Consolidation**

### Phase 3: Advanced (Weeks 9-12)

7. **NewsAgent** (830 lines) → 300 lines + 5 modules
8. **BaseFlow** abstraction
9. **Testing Infrastructure**

### Phase 4: Documentation (Weeks 13-16)

10. **Auto-generate architecture diagrams**
11. **Simplification metrics dashboard**
12. **Agent/service generator**

---

## 🎯 Target Metrics (6 Months)

| Metric         | Baseline     | Target       | Progress |
| -------------- | ------------ | ------------ | -------- |
| Codebase Size  | 15,000 lines | 11,000 lines | TBD      |
| Startup Time   | 200ms        | <150ms       | ✅ 200ms |
| Memory         | 120MB        | <100MB       | ✅ 120MB |
| Test Coverage  | 94.2%        | 98%          | ✅ 94.2% |
| Largest Agent  | 1,597 lines  | <600 lines   | ⚠️ 1,597 |
| Duplicate Code | ~15%         | <5%          | TBD      |

---

## 🛠️ Quick Commands

```bash
# Measure startup performance
python scripts/measure_startup.py

# Run tests with coverage
pytest --cov=src --cov-report=html

# Generate complexity report
python scripts/complexity_dashboard.py

# Check file sizes
python scripts/check_file_sizes.py

# Validate dependency graph
python scripts/check_circular_deps.py
```

---

## 📚 Key Documents

- **Architecture:** [.github/copilot-instructions.md](.github/copilot-instructions.md)
- **Audit:** [INTEGRATION_ECOSYSTEM_AUDIT.md](INTEGRATION_ECOSYSTEM_AUDIT.md)
- **Success Story:** [JOBCARD_CALENDAR_MODULAR_INTEGRATION.md](JOBCARD_CALENDAR_MODULAR_INTEGRATION.md)

---

## 🆘 When in Doubt

1. **Check principles:** Does this follow the 5 rules?
2. **Check anti-patterns:** Am I doing something forbidden?
3. **Check examples:** See CalendarAgent for proven pattern
4. **Ask team:** Bi-weekly retros, monthly architecture reviews
5. **Document:** Update ADR if architectural decision made

---

**Remember:** Simplification is continuous, not one-time. Every PR is an opportunity to reduce complexity.

**Questions?** See [INTEGRATION_ECOSYSTEM_AUDIT.md](INTEGRATION_ECOSYSTEM_AUDIT.md) or ask in #refactoring channel.
