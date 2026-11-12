"""One trace follows a task from submission to Activity (spec observability/baseline).
Phase 1 PR 2 extends this to the harness's model and tool calls."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from temporalio.client import Client

from common.blob_store.s3 import S3BlobStore
from common.observability import configure_tracing, tracing_interceptor
from common.persistence.repositories import RecordingBlobStore, make_engine
from orchestrator.submit import prepare_task, start_task
from registry.loader import load_registry
from tests.support.fake_model import FakeModel
from tests.support.stack import env, run_hello, run_id
from tests.support.workers import running_workers

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


async def test_task_trace_reaches_model_and_tool_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One trace from submission through TaskWorkflow and run_harness_turn down to
    each model and tool call (Phase 1 accept: one trace follows a task)."""
    exporter = InMemorySpanExporter()
    provider = configure_tracing("praxismesh-test", exporter)
    steps = [
        {"tool": "lookup_price", "args": {"sku": "SKU-1"}},
        {"tool": "finish_task", "args": {"status": "done", "summary": "traced"}},
    ]
    with FakeModel(steps) as fake:
        monkeypatch.setenv("VLLM_BASE_URL", fake.base_url)
        async with running_workers(tmp_path, provider=provider) as client:
            engine = make_engine()
            s3 = S3BlobStore.from_env()
            await s3.ensure_bucket()
            start = await prepare_task(
                {"profile": "default", "instructions": "Look up SKU-1."},
                load_registry(),
                RecordingBlobStore(s3, engine),
                base_dir=tmp_path,
            )
            await engine.dispose()
            tracer = provider.get_tracer("test")
            with tracer.start_as_current_span("praxis.task.submit") as root:
                handle = await start_task(client, start)
            await handle.result()
    provider.force_flush()
    spans = exporter.get_finished_spans()
    by_id = {s.context.span_id: s for s in spans}

    def ancestors(span: Any) -> list[str]:
        names = []
        while span.parent is not None and span.parent.span_id in by_id:
            span = by_id[span.parent.span_id]
            names.append(span.name)
        return names

    trace_id = root.get_span_context().trace_id
    model = [s for s in spans if s.name == "model call"]
    tools = [s for s in spans if s.name == "tool call"]
    assert len(model) == 2 and {(s.attributes or {}).get("praxis.tool") for s in tools} >= {
        "lookup_price"
    }
    for span in [*model, *tools]:
        assert span.context.trace_id == trace_id
        chain = ancestors(span)
        assert any(n.startswith("RunActivity:run_harness_turn") for n in chain)
        assert "praxis.task.submit" in chain
