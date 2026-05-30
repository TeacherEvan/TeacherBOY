#!/bin/bash
# HF Space Cleanup Script
# Removes unnecessary documentation and development files from HF Space deployment
# These files are already excluded from Docker image via .dockerignore but clutter the repo

set -e

echo "🧹 Zeus HF Space Cleanup - Removing unnecessary files..."
echo ""
echo "⚠️  WARNING: This will remove docs/ and tests/ directories!"
echo "⚠️  Only run this on hf-deploy branch, NEVER on main!"
echo ""
read -p "Continue? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 1
fi

# Directories to REMOVE:
echo "📁 Removing development documentation directories..."
[ -d "docs" ] && git rm -rf docs/ && echo "  ✓ docs/ removed"
[ -d "tests" ] && git rm -rf tests/ && echo "  ✓ tests/ removed"
[ -d "python-connector-api" ] && git rm -rf python-connector-api/ && echo "  ✓ python-connector-api/ removed"
[ -d "test_calendar_data" ] && git rm -rf test_calendar_data/ && echo "  ✓ test_calendar_data/ removed"

# Documentation MD files to REMOVE (keep only README.md and LICENSE):
echo ""
echo "📄 Removing documentation markdown files..."

# List of docs to remove
DOCS_TO_REMOVE=(
    "ARCHITECTURE.md"
    "CODE_REVIEW.md"
    "COMPREHENSIVE_TECHNICAL_REVIEW.md"
    "CHANGELOG.md"
    "CALENDAR_DUPLICATE_PREVENTION.md"
    "CALENDAR_PERSISTENCE_FIX.md"
    "CALENDAR_SCRAPING_FIXES_SUMMARY.md"
    "DEPLOYMENT_GUIDE.md"
    "QUICK_START.md"
    "QUICK_REFERENCE.md"
    "DOCUMENTATION_AUDIT_PHASE4_STANDARDIZATION.md"
    "DOCUMENTATION_DEBT_BACKLOG.md"
    "DOCUMENTATION_INDEX.md"
    "DOCUMENTATION_MAINTENANCE_PROTOCOLS.md"
    "FIX_SUMMARY_REPLY_TOKEN.md"
    "IMPLEMENTATION_SUMMARY.md"
    "UX_FIXES_SUMMARY.md"
    "OPTIMIZATION_IMPLEMENTATION_SUMMARY.md"
    "OPTIMIZATION_QUICK_START.md"
    "OPTIMIZATION_REPORT.md"
    "OPTIMIZATION_SUMMARY.md"
    "PRODUCTIVITY_OPTIMIZATION_PLAN.md"
    "SECURITY.md"
    "temp_handler_code.txt"
    "form_translation.txt"
    "test_output.txt"
    "workspace_non_critical_issues.json"
    "JOBCARD.md"
)

for file in "${DOCS_TO_REMOVE[@]}"; do
    [ -f "$file" ] && git rm -f "$file" 2>/dev/null && echo "  ✓ $file"
done

echo ""
echo "✅ Cleanup complete!"
echo ""
echo "📊 Next steps:"
echo "  1. Review: git status"
echo "  2. Commit: git commit -m 'chore(hf): minimal production build'"
echo "  3. Push to HF: git push hf hf-deploy:main --force"
echo ""
