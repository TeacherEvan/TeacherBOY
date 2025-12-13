# Deployment

This guide focuses on production-friendly deployment patterns.

## Recommended options

- Render: simplest “set it and forget it” HTTPS hosting
- Azure Container Apps: best option if you’re already on Azure
- VPS + Docker + reverse proxy: most control

## Common requirements

- Your bot must be reachable via **HTTPS** on `POST /webhook`
- Keep secrets out of Git (use host “Secrets/Env Vars”)
- Disable LINE auto-replies so your bot is the only responder

## Local testing (ngrok)

Use this to validate your bot before deploying.

1. Run the bot (Docker):

   ```bash
   docker build -t teacherboy .
   docker run --env-file .env -p 8000:8000 teacherboy
   ```

2. Start ngrok:

   ```bash
   ngrok http 8000
   ```

3. Set webhook to `https://<ngrok-id>.ngrok.io/webhook`.

## Render (recommended)

1. Create a new Render **Web Service** from this Git repo.
2. Runtime: Docker.
3. Internal port: `8000`.
4. Add env vars/secrets:

   - `LINE_CHANNEL_SECRET`
   - `LINE_CHANNEL_ACCESS_TOKEN`
   - `GOOGLE_TRANSLATE_API_KEY` (recommended)
   - Optional bootstrap: `ADMIN_SETUP_KEY`

5. Deploy.
6. Set LINE webhook to `https://<service>.onrender.com/webhook`.

## Hugging Face Spaces (Docker)

This repo is compatible with **Docker Spaces**.

Key notes:

- Your Space must be **Public** for LINE to reach your webhook.
- Configure LINE to call: `https://<your-space-host>.hf.space/webhook`
- Store secrets in **Space Settings → Secrets** (do not commit `.env`).

### Push updates (recommended workflow)

Spaces are git repos. Pushing triggers an automatic rebuild/restart.

1. Add the Space as a remote (once):

   ```bash
   git remote add hf https://huggingface.co/spaces/<owner>/<space>
   # Example:
   git remote add hf https://huggingface.co/spaces/EvilEvan/TeacherBOY
   ```

2. Commit your changes locally:

   ```bash
   git add .
   git commit -m "Update"
   ```

3. Push to Hugging Face:

   ```bash
   git push hf main
   ```

   Authentication:

   - Username: your Hugging Face username
   - Password: a Hugging Face **Access Token** (not your account password)

If you initially uploaded files via the web UI, the Space may have a different git history.
If you control the Space and want your local repo to be the source of truth, you can sync with:

```bash
git push --force-with-lease hf main
```

### VS Code one-click push

This repo includes tasks:

- `hf:set-remote`
- `hf:push`

Run them via **Tasks: Run Task**.

## Azure Container Apps

High-level flow:

1. Build/push image to ACR.
2. Create Container App pointing at the image.
3. Ingress: External, target port `8000`.
4. Set secrets/env vars (same as above).
5. Set LINE webhook to `https://<your-app>.<region>.azurecontainerapps.io/webhook`.

## VPS + Docker

1. Provision a VPS and install Docker.
2. Copy `.env` to the server (do not commit).
3. Run:

   ```bash
   docker build -t teacherboy .
   docker run -d --name teacherboy --env-file .env -p 8000:8000 --restart unless-stopped teacherboy
   ```

4. Put a reverse proxy (nginx/caddy) in front to terminate TLS.

## Admin bootstrap (recommended)

If you didn’t set `ADMIN_USER_IDS` yet, you can bootstrap safely:

- Set `ADMIN_SETUP_KEY` temporarily.
- In LINE, message: `/admin claim <ADMIN_SETUP_KEY>`.
- Use the returned user id to set `ADMIN_USER_IDS`, restart, then remove `ADMIN_SETUP_KEY`.
