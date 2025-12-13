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
