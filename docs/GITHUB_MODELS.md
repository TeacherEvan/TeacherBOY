# GitHub Models Integration Guide

This guide explains how to use **GitHub Models** as your primary LLM provider for Zeus, as an alternative to OpenRouter.

## 🎯 Overview

GitHub Models is a **free AI inference API** that lets you access state-of-the-art models like:
- **OpenAI GPT-4o, GPT-4o-mini, GPT-4.1**
- **xAI Grok-3, Grok-3-mini**
- **DeepSeek-R1**
- **Meta Llama 3.3 70B**
- And many more at [github.com/marketplace/models](https://github.com/marketplace/models)

### Why Use GitHub Models?

| Feature | GitHub Models | OpenRouter |
|---------|--------------|------------|
| **Cost** | Free tier included | Pay per token |
| **Auth** | GitHub PAT | API key |
| **Rate Limits** | 15-150 req/day (free) | Varies by credit |
| **Models** | GPT-4o, Grok, DeepSeek | 100+ models |

---

## 📋 Prerequisites

1. A GitHub account (free tier works!)
2. GitHub Personal Access Token (PAT) with `models:read` scope

---

## 🔧 Setup Instructions

### Step 1: Create a GitHub PAT

1. Go to [github.com/settings/tokens](https://github.com/settings/tokens)
2. Click **"Generate new token"** → **"Fine-grained token"** (recommended)
3. Set:
   - **Token name:** `Zeus-LLM` (or any name)
   - **Expiration:** 90 days (or custom)
   - **Repository access:** No repositories needed
   - **Permissions:** Under "Account permissions", enable:
     - `models:read` ✅
4. Click **Generate token**
5. Copy the token (starts with `github_pat_...`)

### Step 2: Configure Zeus

Add these environment variables to your `.env` file or deployment secrets:

```bash
# GitHub Models Configuration
GITHUB_MODELS_PAT=github_pat_your_token_here
GITHUB_MODELS_DEFAULT_MODEL=openai/gpt-4o

# Optional: Set provider priority (default: github first)
LLM_PROVIDER_PRIORITY=github,openrouter
```

### Step 3: Restart Zeus

```bash
# Local development
python -m uvicorn src.main:app --reload

# Docker
docker-compose up --build
```

---

## 🚀 Available Models

Visit [github.com/marketplace/models](https://github.com/marketplace/models) for the full list.

### Recommended Models

| Model ID | Description | Rate Limit Tier |
|----------|-------------|-----------------|
| `openai/gpt-4o` | Best overall, multimodal | Low |
| `openai/gpt-4o-mini` | Fast, cost-effective | Low |
| `xai/grok-3` | X.AI's latest | Special (1 rpm) |
| `xai/grok-3-mini` | Faster Grok variant | Special (2 rpm) |
| `deepseek/deepseek-r1` | Reasoning specialist | Special (1 rpm) |
| `meta/llama-3.3-70b-instruct` | Open weights | Low |

---

## ⚡ Rate Limits

GitHub Models has tiered rate limits based on your Copilot subscription:

| Tier | Requests/Min | Requests/Day | Tokens (in/out) |
|------|--------------|--------------|-----------------|
| **Low** (most models) | 15 | 150 | 8000/4000 |
| **High** (large models) | 10 | 50 | 8000/4000 |
| **Grok-3** | 1 | 15 | 4000/4000 |
| **DeepSeek-R1** | 1 | 8 | 4000/4000 |

Zeus automatically handles rate limits with exponential backoff retry.

---

## 🔄 Provider Priority

You can configure which LLM provider Zeus uses first:

```bash
# Try GitHub Models first, fall back to OpenRouter
LLM_PROVIDER_PRIORITY=github,openrouter

# Try OpenRouter first, fall back to GitHub Models
LLM_PROVIDER_PRIORITY=openrouter,github
```

If the primary provider fails (rate limited, error), Zeus automatically tries the fallback.

---

## 🧪 Testing the Integration

Send a message to your LINE bot:

```
Zeus What is the capital of France?
```

Check the logs for:
```
🤖 GitHub Models response from openai/gpt-4o (523 chars, 42+127 tokens)
✅ Sent LLM response via GitHub Models for 'What is the capital...'
```

---

## 🐛 Troubleshooting

### "No LLM service configured"

- Ensure `GITHUB_MODELS_PAT` is set
- Check the PAT has `models:read` permission

### "Rate limit exceeded (429)"

- Free tier: 150 requests/day for most models
- Wait for the rate limit to reset (usually 1 minute for rpm, 24h for rpd)
- Consider using a lower-tier model

### "Model not available (404)"

- Check the model ID at [github.com/marketplace/models](https://github.com/marketplace/models)
- Update `GITHUB_MODELS_DEFAULT_MODEL` to a valid model

### "Authentication failed (401)"

- Regenerate your PAT at [github.com/settings/tokens](https://github.com/settings/tokens)
- Ensure `models:read` permission is enabled

---

## 📚 API Reference

GitHub Models uses an OpenAI-compatible API:

**Endpoint:** `https://models.github.ai/inference/chat/completions`

**Headers:**
```http
Authorization: Bearer YOUR_GITHUB_PAT
X-GitHub-Api-Version: 2022-11-28
Content-Type: application/json
```

**Request Body:**
```json
{
  "model": "openai/gpt-4o",
  "messages": [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Hello!"}
  ],
  "temperature": 0.7
}
```

**Response:**
```json
{
  "choices": [
    {
      "message": {
        "role": "assistant",
        "content": "Hello! How can I help you today?"
      }
    }
  ],
  "usage": {
    "prompt_tokens": 25,
    "completion_tokens": 10
  }
}
```

---

## 🔗 Resources

- [GitHub Models Documentation](https://docs.github.com/en/github-models)
- [Model Marketplace](https://github.com/marketplace/models)
- [API Reference](https://docs.github.com/en/rest/models)
- [Rate Limits](https://docs.github.com/en/github-models/use-github-models/prototyping-with-ai-models#rate-limits)
