"""OpenTelemetry tracing setup for the assistant service.

This module wires up OpenTelemetry tracing with:
- FastAPI auto-instrumentation (incoming requests)
- httpx auto-instrumentation (outgoing HTTP calls)
- Logging auto-instrumentation (captures application logs)
- OTLP exporter (default: AI Toolkit collector on localhost)

Tracing is intentionally optional and controlled by Settings.enable_tracing.
"""

from __future__ import annotations

import importlib
import logging
from contextlib import contextmanager

from fastapi import FastAPI

from src.config import Settings

logger = logging.getLogger(__name__)

_TRACING_INITIALIZED = False


class _SafeOTLPExporter:
    """Proxy around OTLPSpanExporter that swallows connection errors.

    OTLPSpanExporter opens its socket lazily on the first export(), so an
    unreachable collector (e.g. AI Toolkit not running on localhost:4318) is not
    detected at setup time; instead the BatchSpanProcessor's background thread
    raises ConnectionRefusedError and spams ERROR tracebacks. Wrapping export()
    lets us silently return FAILURE instead of letting the SDK log the exception.
    """

    def __init__(self, exporter, endpoint: str) -> None:
        self._exporter = exporter
        self._endpoint = endpoint

    def export(self, spans):  # type: ignore[no-untyped-def]
        try:
            return self._exporter.export(spans)
        except Exception as exc:  # noqa: BLE001 - downgrade noisy transport errors
            if _is_connection_error(exc):
                _sdk_trace_export = importlib.import_module("opentelemetry.sdk.trace.export")
                logger.debug(
                    "OTLP export skipped: collector unavailable at %s (%s)",
                    self._endpoint,
                    type(exc).__name__,
                )
                return _sdk_trace_export.SpanExportResult.FAILURE
            raise

    def shutdown(self) -> None:  # type: ignore[no-untyped-def]
        self._exporter.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:  # type: ignore[no-untyped-def]
        return self._exporter.force_flush(timeout_millis)


def _is_connection_error(exc: Exception) -> bool:
    try:
        requests_mod = importlib.import_module("requests")
        urllib3_mod = importlib.import_module("urllib3")
        connection_errors = (
            requests_mod.exceptions.ConnectionError,
            urllib3_mod.exceptions.NewConnectionError,
            ConnectionError,
            OSError,
        )
    except Exception:
        connection_errors = (ConnectionError, OSError)
    return isinstance(exc, connection_errors)


def setup_tracing(app: FastAPI, settings: Settings) -> None:
    """Initialize OpenTelemetry tracing if enabled.

    Safe to call multiple times; subsequent calls become no-ops.
    """
    global _TRACING_INITIALIZED
    if _TRACING_INITIALIZED:
        return

    if not getattr(settings, "enable_tracing", False):
        return

    try:
        trace = importlib.import_module("opentelemetry.trace")
        sdk_resources = importlib.import_module("opentelemetry.sdk.resources")
        sdk_trace = importlib.import_module("opentelemetry.sdk.trace")
        sdk_trace_export = importlib.import_module("opentelemetry.sdk.trace.export")
        otlp_exporter = importlib.import_module("opentelemetry.exporter.otlp.proto.http.trace_exporter")
        fastapi_instrumentation = importlib.import_module("opentelemetry.instrumentation.fastapi")
        httpx_instrumentation = importlib.import_module("opentelemetry.instrumentation.httpx")
        logging_instrumentation = importlib.import_module("opentelemetry.instrumentation.logging")

        Resource = sdk_resources.Resource
        TracerProvider = sdk_trace.TracerProvider
        BatchSpanProcessor = sdk_trace_export.BatchSpanProcessor
        OTLPSpanExporter = otlp_exporter.OTLPSpanExporter
        ConsoleSpanExporter = sdk_trace_export.ConsoleSpanExporter
        FastAPIInstrumentor = fastapi_instrumentation.FastAPIInstrumentor
        HTTPXClientInstrumentor = httpx_instrumentation.HTTPXClientInstrumentor
        LoggingInstrumentor = logging_instrumentation.LoggingInstrumentor

        # If someone already configured a provider elsewhere, don't replace it.
        current_provider = trace.get_tracer_provider()
        if isinstance(current_provider, TracerProvider):
            provider = current_provider
        else:
            resource = Resource.create({"service.name": settings.otel_service_name})
            provider = TracerProvider(resource=resource)

            # Try OTLP exporter first, fall back to console
            try:
                otlp_exporter_instance = OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint)
                safe_exporter = _SafeOTLPExporter(otlp_exporter_instance, settings.otel_exporter_otlp_endpoint)
                provider.add_span_processor(BatchSpanProcessor(safe_exporter))
                logger.info(
                    "✅ Tracing enabled with OTLP exporter (service=%s, otlp=%s)",
                    settings.otel_service_name,
                    settings.otel_exporter_otlp_endpoint,
                )
            except Exception as otlp_error:
                # Fall back to console exporter
                console_exporter_instance = ConsoleSpanExporter()
                provider.add_span_processor(BatchSpanProcessor(console_exporter_instance))
                logger.warning(
                    "⚠️  OTLP exporter failed, falling back to console exporter: %s",
                    otlp_error,
                )

        trace.set_tracer_provider(provider)

        # Auto-instrumentation.
        FastAPIInstrumentor.instrument_app(app)
        HTTPXClientInstrumentor().instrument()
        LoggingInstrumentor().instrument(set_logging_format=True)

        logger.info("✅ Tracing fully initialized")
        _TRACING_INITIALIZED = True

    except Exception as e:
        # Tracing must never block startup.
        logger.warning("⚠️  Tracing setup failed: %s", e, exc_info=True)


def get_tracer(name: str | None = None):
    """Return an OpenTelemetry tracer (safe even if tracing is disabled)."""

    try:
        trace = importlib.import_module("opentelemetry.trace")
        return trace.get_tracer(name or __name__)
    except Exception:
        # If opentelemetry isn't installed, return a minimal no-op tracer.
        class _NoopSpan:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def set_attribute(self, *_args, **_kwargs):
                return None

        class _NoopTracer:
            def start_as_current_span(self, *_args, **_kwargs):
                return _NoopSpan()

        return _NoopTracer()


@contextmanager
def create_span(name: str, attributes: dict | None = None):
    """
    Create a span for a specific operation (agent, service, etc).

    Usage:
        with create_span("agent.translation", {"chat_id": "user_123"}) as span:
            # do work
            span.set_attribute("result", "success")

    Args:
        name: Span name (e.g., "agent.translation")
        attributes: Optional dict of attributes to set on the span

    Yields:
        OpenTelemetry span context manager
    """
    tracer = get_tracer(__name__)
    with tracer.start_as_current_span(name) as span:
        if attributes:
            for key, value in attributes.items():
                # Convert non-primitives to strings for OTLP compatibility
                attr_val = value if isinstance(value, (bool, int, float, str)) else str(value)
                span.set_attribute(key, attr_val)
        yield span
