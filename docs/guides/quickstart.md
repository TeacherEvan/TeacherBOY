# Quick Start

Goal: run Ms. Green locally (Docker) and connect it to LINE.

## Prerequisites

- LINE Official Account + Messaging API channel
- Docker Desktop installed
- A public HTTPS URL for the webhook (ngrok for local testing is fine)

## 1) Configure environment

1. Copy the template:

   ```bash
   cp .env.example .env
   ```

2. Fill in at minimum:
   - `LINE_CHANNEL_SECRET`
   - `LINE_CHANNEL_ACCESS_TOKEN`

3. Recommended (better translation quality):
   - `GOOGLE_TRANSLATE_API_KEY`

## 2) Run the bot

### Option A: Docker (recommended)

```bash
docker build -t ms-green-assistant .
docker run --env-file .env -p 8000:8000 ms-green-assistant
```

Health endpoints:

- `GET http://localhost:8000/health` — process liveness, always cheap
- `GET http://localhost:8000/readiness` — startup readiness, may return `503`
   until startup data is loaded and agents are registered

### Option B: Python (dev)

```bash
pip install -r requirements.txt
python -m uvicorn src.main:app --reload --port 8000
```

## 3) Expose a public webhook URL (local testing)

```bash
ngrok http 8000
```

Copy the HTTPS URL (example: `https://abc123.ngrok.io`). Your webhook becomes:

- `https://abc123.ngrok.io/webhook`

## 4) Configure LINE

Follow: [docs/guides/line-setup.md](line-setup.md)

## 5) Test

- Send a Thai message (e.g., `สวัสดีครับ`) to start translation mode.
- Send English/Thai messages; the bot replies with translations.
- Stop/sleep: `amen`
- Wake: `Dear Ms. Green`

### Optional: AI + Web Search (DM-only for regular users)

- **AI chat:** `Ms. Green <your question>`
- **Web search (Brave Search):** `Ms. Green search <query>`

Access rules:

- **Admins:** can use these commands anywhere
- **Regular users:** must use these commands in **DM (1-on-1)**

## Deploy on Hugging Face Spaces (Docker)

1. Create a Space: <https://huggingface.co/new-space> (SDK: Docker)
2. Add the Space as a git remote and publish from this repo:

   ```bash
   git remote add hf https://huggingface.co/spaces/<owner>/<space>
   git push --force-with-lease hf main:main
   ```

3. Wait for the Space build to finish.
4. In Space settings, add Secrets:
   - `LINE_CHANNEL_SECRET`
   - `LINE_CHANNEL_ACCESS_TOKEN`
   - `GOOGLE_TRANSLATE_API_KEY` (recommended)
   - Optional: `ADMIN_SETUP_KEY`

5. Set LINE webhook URL to:

- `https://<your-username>-<your-space>.hf.space/webhook`

Do not use the Space page URL:

- `https://huggingface.co/spaces/<owner>/<space>`

Gotcha:

- Avoid having both a top-level `src/` and a nested `TeacherBOY/src/`.
   Docker Spaces typically runs `uvicorn src.main:app` from the top-level
   `src/`, so nested code will not take effect unless the Dockerfile copy
   paths are updated.
