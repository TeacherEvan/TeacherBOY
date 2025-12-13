"""OpenTelemetry tracing setup for TeacherBOY.

This module wires up OpenTelemetry tracing with:
- FastAPI auto-instrumentation (incoming requests)
- httpx auto-instrumentation (outgoing HTTP calls)
- OTLP exporter (default: AI Toolkit collector on localhost)

Tracing is intentionally optional and controlled by Settings.enable_tracing.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import FastAPI

from src.config import Settings

logger = logging.getLogger(__name__)


def setup_tracing(app: FastAPI, settings: Settings) -> None:
    """Initialize OpenTelemetry tracing if enabled.

    Safe to call multiple times; subsequent calls become no-ops.
    """

    if not getattr(settings, "enable_tracing", False):
        return

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

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

        logger.info(
            "✅ Tracing enabled (service=%s, otlp=%s)",
            settings.otel_service_name,
            settings.otel_exporter_otlp_endpoint,
        )

    except Exception as e:
        # Tracing must never block startup.
        logger.warning("⚠️  Tracing setup failed: %s", e, exc_info=True)


def get_tracer(name: Optional[str] = None):
    """Return an OpenTelemetry tracer (safe even if tracing is disabled)."""

    try:
        from opentelemetry import trace

        return trace.get_tracer(name or __name__)
    except Exception:
        # If opentelemetry isn't installed, return a minimal no-op context manager.
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
