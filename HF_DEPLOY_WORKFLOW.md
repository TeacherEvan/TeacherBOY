# HF Spaces Deployment Workflow

## Overview

This repo is deployed to **two places**:
1. **GitHub** (`origin`) - Full development repo with all docs/tests
2. **HuggingFace Spaces** (`hf`) - Production deployment (minimal, runtime only)

## Setup HF Space Remote

```bash
# Add HF Space as a remote (one-time setup)
git remote add hf https://huggingface.co/spaces/YOUR_USERNAME/YOUR_SPACE_NAME

# Example:
# git remote add hf https://huggingface.co/spaces/EvilEvan/Zeus
```

## Branch Strategy

- `main` - Full repo (GitHub) - **NEVER clean this!**
- `hf-deploy` - Minimal production branch (HF Spaces only)

## Deploy to HF Spaces (Clean Minimal Build)

### Option 1: One-time Cleanup Push

```bash
# Create deployment branch from main
git checkout -b hf-deploy

# Run cleanup script (removes docs/tests)
./cleanup_hf_space.sh

# Commit cleanup
git add -A
git commit -m "chore(hf): minimal production build for HF Spaces"

# Push ONLY to HF Space (not GitHub!)
git push hf hf-deploy:main --force

# Switch back to main
git checkout main

# Delete local deployment branch
git branch -D hf-deploy
```

### Option 2: Maintain Separate hf-deploy Branch

```bash
# Create persistent deployment branch
git checkout -b hf-deploy main

# Run cleanup
./cleanup_hf_space.sh

# Commit
git add -A
git commit -m "chore(hf): minimal production build"

# Push to HF Spaces
git push hf hf-deploy:main --force

# To sync updates from main later:
git checkout hf-deploy
git merge main
./cleanup_hf_space.sh  # Re-clean if docs added
git add -A
git commit -m "chore(hf): sync from main + cleanup"
git push hf hf-deploy:main --force
```

## What Gets Removed for HF Spaces

**Removed (~900KB, 94 files):**
- `docs/` - All documentation (27 files)
- `tests/` - All test files (38 files)  
- `*.md` - Implementation logs, guides (24 files)
- `python-connector-api/` - Legacy connector
- `test_calendar_data/` - Test fixtures
- Temporary files (*.txt, *.json logs)

**Kept (essential for runtime):**
- `README.md` - Required by HF Spaces
- `LICENSE`
- `src/` - Application code
- `data/` - Runtime data directory
- `scripts/` - Deployment scripts
- `examples/` - Reference code
- `.github/` - CI/CD workflows
- Docker files
- `requirements.txt`

## Important Notes

1. **NEVER push cleanup to GitHub** - Docs are essential there!
2. **ALWAYS use `hf` remote for deployment** - Not `origin`
3. The cleanup is safe - `.dockerignore` already excludes these files from Docker image
4. HF Spaces auto-rebuilds on git push to the Space

## Quick Reference

```bash
# Check remotes
git remote -v

# Push code update to GitHub (with docs)
git push origin main

# Push minimal build to HF Space
git checkout -b hf-deploy main
./cleanup_hf_space.sh
git add -A && git commit -m "chore(hf): production build"
git push hf hf-deploy:main --force
git checkout main && git branch -D hf-deploy

# Verify HF Space deployment
# Go to: https://huggingface.co/spaces/YOUR_USERNAME/YOUR_SPACE_NAME
# Check "Files" tab - should not have docs/ or tests/
```

## File Size Comparison

- **GitHub (full)**: ~4.5MB
- **HF Space (minimal)**: ~3.6MB (~20% smaller, faster clone/build)

## Troubleshooting

**If you accidentally pushed cleanup to GitHub:**
```bash
# Revert locally
git reset --hard HEAD~1

# Force push revert
git push -f origin main
```

**If HF Space shows old files:**
```bash
# Force rebuild on HF Spaces
git push hf hf-deploy:main --force

# Or trigger rebuild in HF Space settings
```

## See Also

- `cleanup_hf_space.sh` - Cleanup script
- `.dockerignore` - Files excluded from Docker image
- HF Spaces Docs: https://huggingface.co/docs/hub/spaces-overview
