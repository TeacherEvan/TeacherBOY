#!/bin/bash
# scripts/deploy_space.sh
# Push code directly to Hugging Face Spaces using HF_TOKEN from .env

set -e

# Change directory to project root if script is run from scripts/
cd "$(dirname "$0")/.."

# Load HF_TOKEN from .env
if [ -f .env ]; then
    HF_TOKEN=$(grep -E "^HF_TOKEN=" .env | cut -d'=' -f2-)
    # Strip quotes if present
    HF_TOKEN="${HF_TOKEN%\"}"
    HF_TOKEN="${HF_TOKEN#\"}"
    HF_TOKEN="${HF_TOKEN%\'}"
    HF_TOKEN="${HF_TOKEN#\'}"
fi

if [ -z "$HF_TOKEN" ]; then
    echo "❌ Error: HF_TOKEN not found in .env"
    exit 1
fi

echo "🚀 Pushing current branch directly to Hugging Face Spaces..."
git push "https://TeacherEvan:${HF_TOKEN}@huggingface.co/spaces/EvilEvan/TeacherBOY.git" HEAD:main --force

echo "✅ Successfully pushed to Hugging Face Spaces!"
