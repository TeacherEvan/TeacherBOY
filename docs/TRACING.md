# Tracing (OpenTelemetry)

TeacherBOY supports OpenTelemetry tracing for:

- Incoming FastAPI requests
- Outgoing `httpx` calls (Google Translate / LibreTranslate)
- Minimal custom spans for agent routing and translation provider selection

## Quick start (VS Code AI Toolkit)

1. In VS Code, open the command palette and run:

   - `AI Toolkit: Open Tracing`

   This starts the local trace collector and opens the trace viewer.

2. Enable tracing in your `.env`:

   ```env
   ENABLE_TRACING=True
   OTEL_SERVICE_NAME=TeacherBOY
   OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
   ```

3. Start the app:

   - Local: `python -m uvicorn src.main:app --reload --port 8000`
   - Docker: `docker-compose up --build`

4. Send a message through LINE (or hit `/webhook` in dev) and check the trace viewer.

## Notes

- Tracing is optional and won’t block startup if exporter/collector isn’t reachable.
- The default AI Toolkit OTLP endpoint is `http://localhost:4318` (HTTP).
