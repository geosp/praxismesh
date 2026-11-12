"""One trace follows a task from submission to Activity (spec observability/baseline).
Phase 1 PR 2 extends this to the harness's model and tool calls."""

from __future__ import annotations

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from temporalio.client import Client

from common.observability import configure_tracing, tracing_interceptor
from tests.support.stack import env, run_hello, run_id

pytestmark = pytest.mark.integration


async def test_trace_parentage() -> None:
    exporter = InMemorySpanExporter()
    provider = configure_tracing("praxismesh-test", exporter)
    client = await Client.connect(
        f"127.0.0.1:{env('TEMPORAL_PORT', '7233')}",
        namespace=env("TEMPORAL_NAMESPACE", "default"),
        interceptors=[tracing_interceptor(provider)],
    )
    tracer = provider.get_tracer("test")
    with tracer.start_as_current_span("praxis.submit") as root:
        await run_hello(client, f"phase1-trace-{run_id()}", "trace")
    provider.force_flush()
    spans = exporter.get_finished_spans()
    by_id = {s.context.span_id: s for s in spans}

    def ancestors(span_id: int) -> list[str]:
        names = []
        span = by_id.get(span_id)
        while span is not None and span.parent is not None:
            span = by_id.get(span.parent.span_id)
            if span is not None:
                names.append(span.name)
        return names

    names = {s.name for s in spans}
    assert {"StartWorkflow:HelloWorkflow", "RunWorkflow:HelloWorkflow"} <= names
    assert any(n.startswith("RunActivity:say_hello") for n in names)
    trace_id = root.get_span_context().trace_id
    assert all(s.context.trace_id == trace_id for s in spans)
    activity = next(s for s in spans if s.name.startswith("RunActivity:say_hello"))
    assert "praxis.submit" in ancestors(activity.context.span_id)
