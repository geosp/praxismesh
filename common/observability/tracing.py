"""Tracing: OpenTelemetry through Temporal's interceptor, and the harness SDK's own
tracing switched off (RFC Phase 1, Observability; design review F5, G5).

Spans are exported over OTLP/HTTP when `OTEL_EXPORTER_OTLP_ENDPOINT` is set, and
nowhere otherwise. Nothing is ever sent to a third-party trace backend.
"""

from __future__ import annotations

import os

from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SimpleSpanProcessor,
    SpanExporter,
)
from temporalio.contrib.opentelemetry import TracingInterceptor


def configure_tracing(service_name: str, exporter: SpanExporter | None = None) -> TracerProvider:
    """A provider for this process. Pass `exporter` in tests (an in-memory one)."""
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    if exporter is not None:
        provider.add_span_processor(SimpleSpanProcessor(exporter))
    elif os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    return provider


def tracing_interceptor(provider: TracerProvider) -> TracingInterceptor:
    """The interceptor for both the Temporal client and the workers."""
    return TracingInterceptor(tracer=provider.get_tracer("praxismesh"))


def disable_sdk_tracing() -> None:
    """Turn off openai-agents tracing. `set_tracing_disabled` alone leaves the
    default processor, which exports to OpenAI, registered; clear it too."""
    from agents import set_trace_processors, set_tracing_disabled

    set_tracing_disabled(True)
    set_trace_processors([])
