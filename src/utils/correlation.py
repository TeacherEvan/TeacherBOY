"""Correlation ID context for request tracing."""

import contextvars

_correlation_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("correlation_id", default=None)


def get_correlation_id() -> str | None:
    """Get the current correlation ID from context."""
    return _correlation_id_var.get()


def set_correlation_id(correlation_id: str) -> contextvars.Token[str | None]:
    """Set the correlation ID for the current context."""
    return _correlation_id_var.set(correlation_id)


def reset_correlation_id(token: contextvars.Token[str | None]) -> None:
    """Reset the correlation ID context."""
    _correlation_id_var.reset(token)