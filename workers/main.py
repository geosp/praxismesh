"""Generic worker (plan §6 workers/; RFC Phase 1: Workers and Compose).

    python -m workers.main orchestrator           # polls `orchestration`
    python -m workers.main template local-default # polls `tpl.local-default`

Settings come from the environment (infra/.env, or Compose for containers):
TEMPORAL_ADDRESS (default 127.0.0.1:TEMPORAL_PORT), the database, S3 and model
settings, METRICS_PORT and PRAXIS_SCRATCH. A worker for a `dsh` template also
needs DSH_CONTROL, the control socket of its paired DSH container's launcher.

The runner comes from the template's `harness` (DSH migration plan D1): `dsh`
templates run on `DshRunner`, after the launcher's runtime digests matched the
registry lock (R17); `openai_agents` templates run on `OpenAIAgentsRunner`.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from opentelemetry.sdk.trace import TracerProvider
from sqlalchemy.ext.asyncio import AsyncEngine
from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.worker import Worker

from common.blob_store import BlobStore
from common.blob_store.s3 import S3BlobStore
from common.errors import CapabilityError
from common.events import TableTransport
from common.observability import (
    configure_logging,
    configure_tracing,
    disable_sdk_tracing,
    tracing_interceptor,
)
from common.observability.metrics import serve_metrics
from common.persistence.repositories import (
    RecordingBlobStore,
    TaskRepository,
    UsageLedgerRepository,
    make_engine,
)
from harness_activity.activity import HarnessActivities, worker_identity
from harness_activity.dsh.launcher_client import LauncherError
from harness_activity.dsh.runner import DshRunner
from harness_activity.runner import OpenAIAgentsRunner, Unserviceable
from orchestrator.activities import OrchestratorActivities
from orchestrator.constants import orchestration_queue, template_queue
from orchestrator.workflow import TaskWorkflow
from registry.loader import (
    REGISTRY_ROOT,
    LoadedTemplate,
    Registry,
    load_registry,
    read_runtime_pins,
)

DEFAULT_DSH_CONTROL = "/attempts/.control.sock"
# Why this process's worker stopped polling, if it did (review F99).
UNSERVICEABLE: list[str] = []
EXIT_UNSERVICEABLE = 3


async def connect(service: str, provider: TracerProvider | None = None) -> Client:
    address = os.environ.get("TEMPORAL_ADDRESS") or (
        f"127.0.0.1:{os.environ.get('TEMPORAL_PORT', '7233')}"
    )
    return await Client.connect(
        address,
        namespace=os.environ.get("TEMPORAL_NAMESPACE", "default"),
        data_converter=pydantic_data_converter,
        interceptors=[tracing_interceptor(provider or configure_tracing(service))],
    )


async def build_harness(
    registry: Registry,
    loaded: LoadedTemplate,
    engine: AsyncEngine,
    blobs: BlobStore,
    identity: str,
    provider: TracerProvider | None = None,
) -> HarnessActivities:
    """The `run_harness_turn` Activities for a template, on the runner its
    `harness` names. A `dsh` worker refuses to serve unless its launcher reports
    the runtime the registry lock pins."""
    harness = loaded.template.harness
    if harness == "dsh":
        control = Path(os.environ.get("DSH_CONTROL", DEFAULT_DSH_CONTROL))
        pinned = read_runtime_pins(REGISTRY_ROOT).get("dsh")
        if pinned is None:
            raise CapabilityError("the registry lock pins no dsh runtime")
        dsh = DshRunner(control, UsageLedgerRepository(engine), blobs, pinned=pinned)
        try:
            await dsh.check()
        except (LauncherError, Unserviceable) as error:
            raise CapabilityError(f"template {loaded.template.ref}: {error}") from error
        # The attempt trees live on the volume shared with the DSH container.
        return HarnessActivities(
            registry,
            engine,
            blobs,
            dsh,
            control.parent,
            identity,
            open_attempt=dsh.open_attempt,
            preflight=dsh.check,
            events=TableTransport(engine),
        )
    if harness == "openai_agents":
        return HarnessActivities(
            registry,
            engine,
            blobs,
            OpenAIAgentsRunner(provider.get_tracer("praxismesh.harness") if provider else None),
            Path(os.environ.get("PRAXIS_SCRATCH", "/tmp/praxis-scratch")),
            identity,
            events=TableTransport(engine),
        )
    raise CapabilityError(
        f"template {loaded.template.ref} uses harness {harness!r}, which has no runner"
    )


async def build_worker(
    client: Client, role: str, template: str | None, provider: TracerProvider | None = None
) -> Worker:
    registry = load_registry()
    engine = make_engine()
    if role == "orchestrator":
        acts = OrchestratorActivities(registry, TaskRepository(engine))
        return Worker(
            client,
            task_queue=orchestration_queue(),
            workflows=[TaskWorkflow],
            activities=[acts.resolve_capabilities, acts.record_task, acts.complete_task],
            identity=worker_identity("orchestrator"),
        )
    assert template is not None
    loaded = registry.templates[template]
    if not os.environ.get(loaded.template.base_url_env):
        # Fail at startup rather than fail every task this worker would take.
        raise CapabilityError(
            f"{loaded.template.base_url_env} is not set: template {loaded.template.ref} "
            "needs a model endpoint (set it in infra/.env)"
        )
    s3 = S3BlobStore.from_env()
    await s3.ensure_bucket()
    identity = worker_identity(template)
    harness = await build_harness(
        registry, loaded, engine, RecordingBlobStore(s3, engine), identity, provider
    )
    worker = Worker(
        client,
        task_queue=template_queue(template),
        activities=[harness.run_harness_turn],
        max_concurrent_activities=loaded.template.concurrency_per_pod,
        identity=identity,
    )

    def stop_polling(reason: str) -> None:
        # R17 (review F99): a worker that cannot serve stops taking turns; it exits
        # non-zero, and its start-up check refuses until the container is fixed.
        UNSERVICEABLE.append(reason)
        asyncio.get_running_loop().create_task(worker.shutdown())

    harness.on_unserviceable = stop_polling
    return worker


async def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="workers.main")
    parser.add_argument("role", choices=["orchestrator", "template"])
    parser.add_argument("template", nargs="?")
    args = parser.parse_args(argv)
    if args.role == "template" and not args.template:
        parser.error("template workers need a template name")
    configure_logging(os.environ.get("LOG_LEVEL", "INFO"))
    disable_sdk_tracing()
    if os.environ.get("METRICS_PORT"):
        serve_metrics(int(os.environ["METRICS_PORT"]))
    provider = configure_tracing(f"praxis-{args.role}")
    client = await connect(f"praxis-{args.role}", provider)
    worker = await build_worker(client, args.role, args.template, provider)
    await worker.run()
    return EXIT_UNSERVICEABLE if UNSERVICEABLE else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
