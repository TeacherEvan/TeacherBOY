# Tracing

Zeus supports optional OpenTelemetry tracing for runtime debugging and performance inspection.

## Enable tracing

Set these environment variables:

```env
ENABLE_TRACING=True
OTEL_SERVICE_NAME=TeacherBOY
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
```

## What gets traced

- FastAPI request handling
- Webhook processing
- Agent routing
- Selected service calls through the shared async runtime

## Local workflow

1. Start an OTLP-compatible collector or tracing backend.
2. Run Zeus normally.
3. In VS Code, use `AI Toolkit: Open Tracing` if you have the AI Toolkit extension configured.

## Notes

- Tracing is off by default.
- It is intended for diagnostics and observability, not required for normal bot operation.

---

**Last Updated:** 2026-05-30  
**Audience:** Developers  
**Status:** Stable
