"""Telemetry helpers: correlation IDs and optional OpenTelemetry spans.

Tracing is optional; when Application Insights is not configured, the span helper is a
no-op so the runtime works locally without extra setup.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator
from uuid import uuid4


def new_correlation_id() -> str:
    """Return a fresh correlation ID for a single request lifecycle."""
    return uuid4().hex


@contextmanager
def span(name: str, **attributes: object) -> Iterator[None]:
    """Start an OpenTelemetry span if tracing is available; otherwise do nothing."""
    try:
        from opentelemetry import trace
    except ImportError:
        yield
        return

    tracer = trace.get_tracer("agent_platform")
    with tracer.start_as_current_span(name) as current:
        for key, value in attributes.items():
            current.set_attribute(key, value)
        yield
