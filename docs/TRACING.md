# Tracing (OpenTelemetry)

Zeus supports comprehensive OpenTelemetry tracing for:

- **Incoming FastAPI requests** (webhook, health checks)
- **Outgoing HTTP calls** (translation APIs, news sources, weather/finance APIs)
- **Application logs** (all logging events captured as trace events)
- **Agent operations** (multi-agent routing, message processing, session state)
- **Custom spans** (translation, news fetches, admin commands)

## Quick Start (VS Code AI Toolkit)

### 1. Start the Trace Collector (CRITICAL!)

In VS Code, open the command palette (`Ctrl+Shift+P`) and run:

```
ai-mlstudio.tracing.open
```

This starts the OTLP receiver on `localhost:4318` and opens the trace viewer.

### 2. Enable Tracing in .env

```env
ENABLE_TRACING=true
OTEL_SERVICE_NAME=Zeus
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
```

### 3. Start Zeus

**Local:**

```bash
python -m uvicorn src.main:app --reload --port 8000
```

**Docker:**

```bash
docker-compose up --build
```

### 4. Trigger a Message

Send a message via LINE and check the trace viewer. You should see:

- ✅ `POST /webhook` HTTP span
- ✅ Agent routing spans
- ✅ Translation/news API call spans
- ✅ Application logs as trace events

## What Gets Traced

### Automatic (No Code Changes)

✅ **HTTP Requests** – incoming FastAPI & outgoing httpx  
✅ **Application Logs** – all logging calls appear as trace events  
✅ **Span Context** – logs include parent span information

### Manual Tracing (Already Implemented)

Tracing already present in:

- `src/agents/agent_router.py` – multi-agent routing
- `src/agents/translation_agent.py` – translation requests
- `src/agents/news_agent.py` – news flow state
- `src/agents/special_news_agent.py` – special news
- `src/agents/admin_agent.py` – admin commands

## Usage

### Using get_tracer()

```python
from src.utils.tracing import get_tracer

tracer = get_tracer(__name__)

with tracer.start_as_current_span("operation.name") as span:
    span.set_attribute("key", "value")
    # your code here
```

### Using create_span() (Simpler)

```python
from src.utils.tracing import create_span

with create_span("operation.name", {"key": "value"}) as span:
    # your code here
    span.set_attribute("result", "success")
```

## Configuration

### Custom OTLP Endpoint

```env
ENABLE_TRACING=true
OTEL_EXPORTER_OTLP_ENDPOINT=https://your-collector.example.com:4318
```

### AI Toolkit Defaults

- **Endpoint:** `http://localhost:4318/v1/traces`
- **Service Name:** `Zeus`

## Troubleshooting

1. ✅ Verify `ENABLE_TRACING=true`
2. ✅ Verify trace collector is running
3. ✅ Check startup logs for `✅ Tracing enabled`
4. ✅ Verify `localhost:4318` is accessible
5. ✅ Send a test message to trigger spans

## Notes

- Tracing is optional and won't block startup if the exporter/collector isn't reachable.
- The default AI Toolkit OTLP endpoint is `http://localhost:4318` (HTTP).
- Logging instrumentation is enabled by default, capturing all log messages as trace events.
- The `create_span()` helper in `src/utils/tracing.py` provides a simplified API for custom spans.

## References

- [OpenTelemetry Python](https://opentelemetry.io/docs/instrumentation/python/)
- [OTLP Spec](https://opentelemetry.io/docs/reference/specification/protocol/)
- [AI Toolkit Tracing](https://marketplace.visualstudio.com/items?itemName=ms-ai-tools.ai-toolkit)
