# Quick Start

Goal: run TeacherBOY locally (Docker) and connect it to LINE.

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
docker build -t teacherboy .
docker run --env-file .env -p 8000:8000 teacherboy
```

Health endpoints:

- `GET http://localhost:8000/health`
- `GET http://localhost:8000/readiness`

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
- Stop/sleep: `Thank you TeacherBoy`
- Wake: `TeacherBoy`

## Deploy on Hugging Face Spaces (Docker)

1. Create a Space: <https://huggingface.co/new-space> (SDK: Docker)
2. Push this repo to the Space (Git remote) and wait for build.
3. In Space settings, add Secrets:

   - `LINE_CHANNEL_SECRET`
   - `LINE_CHANNEL_ACCESS_TOKEN`
   - `GOOGLE_TRANSLATE_API_KEY` (recommended)
   - Optional: `ADMIN_SETUP_KEY`

4. Set LINE webhook URL to:

- `https://<your-username>-<your-space>.hf.space/webhook`
