# Documentation Maintenance Protocols

**Project:** Zeus/TeacherBOY  
**Version:** 1.0.0  
**Last Updated:** 2026-01-08  
**Purpose:** Establish sustainable documentation maintenance practices to prevent drift and ensure quality

---

## Table of Contents

1. [Update Frequency Guidelines](#update-frequency-guidelines)
2. [Documentation Standards Reference](#documentation-standards-reference)
3. [Quality Checklist for New Documentation](#quality-checklist-for-new-documentation)
4. [Review Cycle Process](#review-cycle-process)
5. [Version Control Integration](#version-control-integration)
6. [Automation Tools](#automation-tools)
7. [Responsibility Matrix](#responsibility-matrix)

---

## Update Frequency Guidelines

### By Document Type

| Document Type | Update Frequency | Update Triggers | Owner |
|---------------|------------------|-----------------|-------|
| **README.md** | Per major release | New features, architecture changes | Project Lead |
| **CHANGELOG.md** | Every release | All code changes, bug fixes, features | Development Team |
| **API/Reference Docs** | Per feature release | API changes, new endpoints, deprecations | Backend Developer |
| **User Guides** | Quarterly + as-needed | Feature changes, workflow updates | Documentation Lead |
| **Architecture Docs** | Semi-annually + as-needed | Major refactoring, design changes | Architect |
| **Quick Start/Setup** | Quarterly review | Dependency updates, setup process changes | DevOps/Lead |
| **Feature Documentation** | With feature deployment | New features, feature updates | Feature Owner |
| **Admin Guides** | Quarterly review | New admin commands, policy changes | Admin Team |

### Update Triggers (When to Update Documentation)

**Immediate Updates Required:**
- 🔴 Breaking API changes
- 🔴 New required environment variables
- 🔴 Security-related configuration changes
- 🔴 Deprecated features or commands
- 🔴 Critical bug fixes affecting documented behavior

**Within 1 Week:**
- 🟡 New features or agents
- 🟡 New configuration options
- 🟡 Performance improvements affecting usage
- 🟡 Updated dependencies with new requirements

**Next Sprint/Release:**
- 🟢 Minor bug fixes
- 🟢 Code refactoring (no behavior change)
- 🟢 Internal improvements
- 🟢 Terminology updates

---

## Documentation Standards Reference

### Terminology Dictionary

**Always use these standardized terms** (from Phase 4 audit):

| Concept | Standard Form | Avoid |
|---------|--------------|-------|
| Project name | **Zeus** | TeacherBOY (legacy) |
| LINE service | **LINE Bot**, **LINE Messaging API** | Line bot, linebot |
| User identifier | **LINE user ID** (prose), `user_id` (code) | userid, user id |
| Administrator | **Admin** (heading), **admin** (prose) | administrator |
| Commands | `/admin`, `Zeus <query>` (with backticks) | admin (unformatted) |
| Technical terms | **API**, **LLM**, **HF Hub**, **OTEL** (all caps) | Api, llm, otel |
| Dates | **ISO 8601** (metadata: `YYYY-MM-DD`) | Mixed formats |
| Agent names | **Calendar Agent** (title case in headings) | calendar agent (in titles) |

**Full terminology reference:** [`DOCUMENTATION_AUDIT_PHASE4_STANDARDIZATION.md`](DOCUMENTATION_AUDIT_PHASE4_STANDARDIZATION.md) Section 2.

### Markdown Formatting Standards

**Code Blocks:**
```markdown
Use language identifiers for all code blocks:
```python
# Python code
```

```bash
# Shell commands
```

```json
// JSON configuration
```
\`\`\`

**Links:**
```markdown
# Internal links (relative paths)
[Link text](docs/file.md)
[Link with anchor](docs/file.md#section-name)

# External links (full URLs)
[LINE Developers](https://developers.line.biz/)
```

**Commands and Code References:**
```markdown
Use backticks for inline code: `Zeus help`, `/admin stats`, `user_id`
```

**Emphasis:**
- **Bold** (`**text**`): Important terms, UI elements, emphasis
- _Italic_ (`*text*`): Minimal use (quotes, light emphasis)
- `Code` (`` `text` ``): Commands, filenames, variable names, code elements

**Admonitions (Status Indicators):**
- ✅ Success, completed, verified
- ⚠️ Warning, caution, important
- ❌ Error, forbidden, critical issue
- 🔴 Critical/urgent
- 🟡 Medium priority
- 🟢 Low priority/safe
- 📝 Note
- 🔧 Configuration
- 🚀 Feature/new

### Metadata Requirements

**All new documentation MUST include footer metadata:**

```markdown
---

**Last Updated:** 2026-01-08  
**Applies to Version:** 3.5.0+  
**Audience:** [Developers|Administrators|End Users]  
**Status:** [Stable|Beta|Deprecated]
```

**For feature documentation, also include:**
```markdown
**Feature Version:** 3.5.0  
**Dependencies:** [List key dependencies]  
**Related Commands:** `command1`, `command2`
```

### Code Example Formatting Rules

1. **Always include comments** explaining what code does
2. **Use realistic examples** (not `foo`, `bar`)
3. **Show expected output** when relevant
4. **Highlight environment variables** clearly
5. **Include error handling** in complex examples

**Good Example:**
```python
# Check if user is admin before allowing privileged operation
if user_id in settings.get_admin_user_ids():
    # Admin bypass: unlimited rate limit
    await execute_privileged_operation()
else:
    # Regular users: check rate limit
    if not rate_limiter.check_limit(chat_id):
        await reply_text("Rate limit exceeded. Try again later.")
        return
```

---

## Quality Checklist for New Documentation

### Pre-Publication Checklist

Use this checklist when creating **any new documentation file**:

#### Structure & Basics
- [ ] Has clear H1 title at top of document
- [ ] Includes Table of Contents (if >4 sections)
- [ ] Uses proper heading hierarchy (H1 → H2 → H3, no skipping)
- [ ] Has footer metadata (last updated, version, audience, status)
- [ ] File is in correct location (`docs/` folder structure)

#### Content Quality
- [ ] Uses standardized terminology (see terminology dictionary)
- [ ] All technical terms defined on first use
- [ ] Contains practical, realistic examples
- [ ] Includes troubleshooting section (if applicable)
- [ ] Links to related documentation
- [ ] Prerequisites clearly stated (if applicable)

#### Code & Commands
- [ ] All code blocks have language identifiers (```python, ```bash, etc.)
- [ ] Commands use proper formatting (backticks: `/command`)
- [ ] Code examples include explanatory comments
- [ ] Environment variables clearly marked (`VARIABLE_NAME`)
- [ ] Expected output shown for commands (where helpful)

#### Links & References
- [ ] All internal links use relative paths (`docs/file.md`)
- [ ] All links tested and verified working
- [ ] External links use full URLs with HTTPS
- [ ] Cross-references to related docs included
- [ ] File is listed in [`DOCUMENTATION_INDEX.md`](DOCUMENTATION_INDEX.md)

#### Formatting Consistency
- [ ] Follows markdown best practices
- [ ] Passes markdownlint validation (`.markdownlint.json` config)
- [ ] Passes spell check (cspell validation)
- [ ] Tables properly formatted with headers
- [ ] Lists use consistent formatting (dash for unordered, numbers for ordered)
- [ ] Proper emphasis usage (bold for important, code for technical)

#### Accessibility & Usability
- [ ] Written for intended audience level
- [ ] Clear, concise sentences (avoid jargon where possible)
- [ ] Logical organization (general → specific)
- [ ] Scannability: headings, lists, tables used effectively
- [ ] Action-oriented (tells readers what to do)

### Review Checklist (Before Merging PR)

For documentation **changes/updates**:

- [ ] CHANGELOG.md updated (if user-facing change)
- [ ] Version number updated (if applicable)
- [ ] "Last Updated" date refreshed
- [ ] Related documentation cross-references checked
- [ ] No broken links introduced
- [ ] Terminology consistent with existing docs
- [ ] Examples still accurate and tested

---

## Review Cycle Process

### Quarterly Documentation Audit

**Every 3 months** (Jan, Apr, Jul, Oct), conduct a focused documentation review:

#### Week 1: Automated Checks
1. **Run Link Checker** - Identify broken links
2. **Run Spell Check** - Validate all documentation
3. **Review Metadata** - Check all "Last Updated" dates
4. **Check External Links** - Manually verify external resources

#### Week 2: Content Review
1. **Verify Accuracy** - Do docs match current behavior?
2. **Check Completeness** - New features documented?
3. **Review Examples** - Are code examples still valid?
4. **Test Commands** - Verify all documented commands work

#### Week 3: User Feedback Integration
1. **Review GitHub Issues** - Documentation-related issues
2. **Check Support Questions** - Common confusion points
3. **Update FAQ** - Add frequently asked questions
4. **Improve Clarity** - Rewrite confusing sections

#### Week 4: Improvements & Publishing
1. **Implement Fixes** - Address identified issues
2. **Update Audit Report** - Document findings
3. **Update CHANGELOG** - Record documentation improvements
4. **Publish Changes** - Merge and deploy

### Continuous Review Process

**Peer Review for All Documentation Changes:**

| Change Type | Review Required |
|-------------|----------------|
| New documentation file | 2 reviewers (1 technical, 1 for clarity) |
| Major update (>50% changed) | 2 reviewers |
| Minor update (<50% changed) | 1 reviewer |
| Typo/formatting fix | Self-review + automated checks |
| CHANGELOG entry | 1 reviewer |

**Review Criteria:**
- ✅ Accuracy (technical correctness)
- ✅ Clarity (understandable by target audience)
- ✅ Completeness (all necessary information provided)
- ✅ Consistency (matches existing documentation style)
- ✅ Quality checklist passed

### Flagging Outdated Content

**How to flag content for review:**

1. **In the document itself:**
   ```markdown
   > ⚠️ **NEEDS REVIEW:** This section may be outdated as of [date]. See issue #[number].
   ```

2. **Create a GitHub issue:**
   - Label: `documentation`, `needs-update`
   - Template: Link to specific section needing update
   - Reason: Why it might be outdated

3. **Add to Documentation Debt Backlog:**
   - See [`DOCUMENTATION_DEBT_BACKLOG.md`](DOCUMENTATION_DEBT_BACKLOG.md) (created in Phase 5)

### Archiving Deprecated Documentation

**When a feature is deprecated:**

1. **Do NOT delete documentation immediately**
2. **Mark as deprecated** in the document:
   ```markdown
   > ⚠️ **DEPRECATED:** This feature was deprecated in version 3.5.0 and will be removed in 4.0.0.
   > See [new-feature.md](new-feature.md) for the replacement.
   ```
3. **Update CHANGELOG** with deprecation notice
4. **Keep for 2 major versions** (e.g., deprecated in 3.5, remove docs in 5.0)
5. **Move to `docs/archive/`** folder (create if needed)
6. **Update links** to point to replacement documentation

---

## Version Control Integration

### Documentation Update Workflow

**Branch Strategy:**
```
main (production docs)
  ├── docs/feature-name (new feature docs)
  ├── docs/update-section (doc updates)
  └── docs/audit-fixes (audit-related fixes)
```

**Branch Naming:**
- `docs/feature-name` - New feature documentation
- `docs/update-section-name` - Updates to existing docs
- `docs/audit-YYYY-MM` - Audit fixes
- `docs/typo-fix` - Minor corrections

### Pull Request Requirements

**Every documentation PR must include:**

1. **Clear Description:**
   - What was changed and why
   - Which documents were affected
   - Link to related feature PR (if applicable)

2. **Checklist Completion:**
   - Quality checklist completed (paste in PR)
   - Links verified
   - Spell check passed
   - Markdownlint passed

3. **CHANGELOG Update:**
   - If user-facing documentation change, update [`CHANGELOG.md`](CHANGELOG.md)
   - Use semantic versioning for documentation versions

4. **Related Updates:**
   - If README changed, check if DOCUMENTATION_INDEX needs update
   - If new file added, add to DOCUMENTATION_INDEX
   - If terminology changed, update multiple files for consistency

### CHANGELOG Integration

**When to update CHANGELOG.md:**

- ✅ New documentation file created
- ✅ Major documentation restructure
- ✅ Documentation for new feature added
- ✅ Significant corrections to existing docs
- ❌ Typo fixes (too minor)
- ❌ Formatting changes (too minor)
- ❌ Internal documentation updates

**CHANGELOG entry format:**
```markdown
## [3.5.1] - 2026-01-08

### 📚 Documentation

- **New:** Added comprehensive Image Analyzer usage guide
- **Updated:** Deployment guide now includes Kubernetes instructions
- **Fixed:** Corrected LINE webhook URL in Quick Start guide
- **Improved:** Enhanced Calendar Agent examples with real-world scenarios
```

### Commit Message Format

**For documentation commits:**

```
docs: Brief description of change

- Detailed bullet point 1
- Detailed bullet point 2

Closes #123 (if applicable)
```

**Examples:**
```
docs: Add metadata to all user guides

- Added footer metadata to quickstart.md
- Added footer metadata to deployment.md
- Standardized date format to ISO 8601

Relates to documentation audit Phase 5
```

```
docs: Create Image Analyzer usage guide

- New comprehensive guide with examples
- Rate limiting documentation
- Troubleshooting section
- Integration with help system

Closes #456
```

---

## Automation Tools

### Existing Tools (Already Configured)

#### 1. Markdownlint

**Configuration:** [`.markdownlint.json`](.markdownlint.json)

**Usage:**
```bash
# Install (if not already installed)
npm install -g markdownlint-cli

# Check all markdown files
markdownlint '**/*.md' --ignore node_modules

# Check specific file
markdownlint docs/guides/quickstart.md

# Auto-fix simple issues
markdownlint --fix '**/*.md'
```

**What it checks:**
- Heading hierarchy
- List formatting
- Line length (disabled for flexibility)
- Trailing spaces
- Code block formatting

#### 2. Spell Checker (cspell)

**Configuration:** [`cspell.json`](cspell.json)

**Usage:**
```bash
# Install
npm install -g cspell

# Check all files
cspell "**/*.md"

# Check specific file
cspell docs/guides/quickstart.md

# Add word to dictionary (edit cspell.json)
```

**Project-specific dictionary includes:**
- Zeus, TeacherBOY
- LINE, OpenRouter, Hugging Face
- Technical terms (async, webhook, LLM, etc.)

### Recommended Additional Tools

#### 3. Link Checker

**Tool:** `markdown-link-check`

**Installation:**
```bash
npm install -g markdown-link-check
```

**Usage:**
```bash
# Check a single file
markdown-link-check README.md

# Check all markdown files
find . -name '*.md' -not -path './node_modules/*' -exec markdown-link-check {} \;
```

**Recommended:** Add to CI/CD pipeline (GitHub Actions)

#### 4. Documentation Coverage Metrics

**Tool:** Custom script (create `scripts/doc-coverage.py`)

**Purpose:**
- Track which modules have documentation
- Identify undocumented features
- Monitor documentation completeness over time

**Metrics to track:**
- Number of documented vs. undocumented agents
- Number of documented vs. undocumented services
- Percentage of code with docstrings

#### 5. Automated Timestamp Updates

**Tool:** Pre-commit hook

**Create:** `.git/hooks/pre-commit`
```bash
#!/bin/bash
# Update "Last Updated" dates in modified markdown files

git diff --cached --name-only --diff-filter=ACM | grep '\.md$' | while read file; do
  if grep -q "Last Updated:" "$file"; then
    sed -i "s/Last Updated: .*/Last Updated: $(date +%Y-%m-%d)/" "$file"
    git add "$file"
  fi
done
```

### CI/CD Integration (GitHub Actions)

**Recommended workflow:** `.github/workflows/docs-validation.yml`

```yaml
name: Documentation Validation

on:
  pull_request:
    paths:
      - '**.md'
      - 'docs/**'

jobs:
  validate-docs:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Install Node.js
        uses: actions/setup-node@v3
        with:
          node-version: '18'
      
      - name: Install validation tools
        run: |
          npm install -g markdownlint-cli
          npm install -g cspell
          npm install -g markdown-link-check
      
      - name: Run markdownlint
        run: markdownlint '**/*.md' --ignore node_modules
      
      - name: Run spell check
        run: cspell "**/*.md"
      
      - name: Check internal links
        run: markdown-link-check --config .markdown-link-check.json README.md
      
      - name: Validate documentation structure
        run: python scripts/validate-docs-structure.py
```

**Benefits:**
- Catches errors before merge
- Enforces standards automatically
- Reduces manual review burden
- Provides fast feedback to contributors

---

## Responsibility Matrix

### Documentation Ownership by Type

| Documentation Type | Primary Owner | Backup | Review Frequency |
|-------------------|---------------|---------|------------------|
| README.md | Project Lead | Architect | Per major release |
| CHANGELOG.md | Release Manager | Dev Team | Every release |
| Architecture docs | Architect | Senior Developer | Quarterly |
| API/Reference docs | Backend Lead | API developers | Per feature release |
| User Guides | Documentation Lead | Product Manager | Quarterly |
| Admin Guides | DevOps Lead | Admin Team | Quarterly |
| Feature docs | Feature Owner | Tech Writer | With feature updates |
| Quick Start | DevOps/Onboarding | Documentation Lead | Quarterly |
| Deployment docs | DevOps Lead | SRE Team | Quarterly |
| Security docs | Security Lead | DevOps | Semi-annually |

### Escalation Path

**For documentation issues:**

1. **Minor issues** (typos, formatting) → Anyone can fix via PR
2. **Content questions** → Document owner (see matrix above)
3. **Architecture questions** → Architect or Senior Developer
4. **Terminology disputes** → Project Lead + Documentation Lead
5. **Large-scale changes** → Project Lead approval required

### Review Assignments

**Automatic PR review assignment** (configure in GitHub):

- **docs/architecture/** → Architect + Senior Developer
- **docs/guides/** → Documentation Lead + relevant feature owner
- **docs/reference/** → Technical Lead + Backend Developer
- **README.md, CHANGELOG.md** → Project Lead
- **All other docs/** → Documentation Lead + 1 subject matter expert

---

## Quick Start for Contributors

**New to documentation? Follow these 5 steps:**

1. **Read the standards** (this document, Section 2)
2. **Use the checklist** (Section 3) before submitting
3. **Follow branch naming** (Section 5)
4. **Run validation tools** (Section 6)
5. **Request peer review** (Section 4)

**Most common mistakes to avoid:**

- ❌ Not using backticks for commands/code
- ❌ Forgetting to update CHANGELOG.md
- ❌ Using absolute paths for internal links
- ❌ Missing code block language identifiers
- ❌ Not adding new files to DOCUMENTATION_INDEX.md
- ❌ Forgetting footer metadata
- ❌ Using "TeacherBOY" instead of "Zeus" in new docs

---

## Appendix: Related Documentation

- **Phase 4 Audit Report:** [`DOCUMENTATION_AUDIT_PHASE4_STANDARDIZATION.md`](DOCUMENTATION_AUDIT_PHASE4_STANDARDIZATION.md)
- **Final Audit Summary:** [`DOCUMENTATION_AUDIT_FINAL_REPORT.md`](DOCUMENTATION_AUDIT_FINAL_REPORT.md)
- **Documentation Index:** [`DOCUMENTATION_INDEX.md`](DOCUMENTATION_INDEX.md)
- **Contribution Guidelines:** `CONTRIBUTING.md` (to be created)

---

**Document Version:** 1.0.0  
**Last Updated:** 2026-01-08  
**Maintained By:** Documentation Lead  
**Review Cycle:** Semi-annually (January, July)  
**Next Review Due:** 2026-07-08
