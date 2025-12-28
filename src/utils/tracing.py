"""OpenTelemetry tracing setup for Zeus.

This module wires up OpenTelemetry tracing with:
- FastAPI auto-instrumentation (incoming requests)
- httpx auto-instrumentation (outgoing HTTP calls)
- Logging auto-instrumentation (captures application logs)
- OTLP exporter (default: AI Toolkit collector on localhost)

Tracing is intentionally optional and controlled by Settings.enable_tracing.
"""

from __future__ import annotations

import logging
import importlib
from typing import Optional
from contextlib import contextmanager

from fastapi import FastAPI

from src.config import Settings

logger = logging.getLogger(__name__)

_TRACING_INITIALIZED = False


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
        otlp_exporter = importlib.import_module(
            "opentelemetry.exporter.otlp.proto.http.trace_exporter"
        )
        fastapi_instrumentation = importlib.import_module(
            "opentelemetry.instrumentation.fastapi"
        )
        httpx_instrumentation = importlib.import_module(
            "opentelemetry.instrumentation.httpx"
        )
        logging_instrumentation = importlib.import_module(
            "opentelemetry.instrumentation.logging"
        )

        Resource = getattr(sdk_resources, "Resource")
        TracerProvider = getattr(sdk_trace, "TracerProvider")
        BatchSpanProcessor = getattr(sdk_trace_export, "BatchSpanProcessor")
        OTLPSpanExporter = getattr(otlp_exporter, "OTLPSpanExporter")
        FastAPIInstrumentor = getattr(fastapi_instrumentation, "FastAPIInstrumentor")
        HTTPXClientInstrumentor = getattr(
            httpx_instrumentation, "HTTPXClientInstrumentor"
        )
        LoggingInstrumentor = getattr(logging_instrumentation, "LoggingInstrumentor")

        # If someone already configured a provider elsewhere, don't replace it.
        current_provider = trace.get_tracer_provider()
        if isinstance(current_provider, TracerProvider):
            provider = current_provider
        else:
            resource = Resource.create({"service.name": settings.otel_service_name})
            provider = TracerProvider(resource=resource)
            exporter = OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint)
            provider.add_span_processor(BatchSpanProcessor(exporter))
            trace.set_tracer_provider(provider)

        # Auto-instrumentation.
        FastAPIInstrumentor.instrument_app(app)
        HTTPXClientInstrumentor().instrument()
        LoggingInstrumentor().instrument(set_logging_format=True)

        logger.info(
            "✅ Tracing enabled (service=%s, otlp=%s)",
            settings.otel_service_name,
            settings.otel_exporter_otlp_endpoint,
        )
        _TRACING_INITIALIZED = True

    except Exception as e:
        # Tracing must never block startup.
        logger.warning("⚠️  Tracing setup failed: %s", e, exc_info=True)


def get_tracer(name: Optional[str] = None):
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
def create_span(name: str, attributes: Optional[dict] = None):
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
