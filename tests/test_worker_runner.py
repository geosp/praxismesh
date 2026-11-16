"""The worker chooses its runner from `template.harness` (DSH migration plan D1,
R17; phase 02 task 1.3)."""

from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from common.blob_store import MemoryBlobStore
from common.errors import CapabilityError
from harness_activity.dsh.runner import DshRunner
from harness_activity.runner import OpenAIAgentsRunner
from harness_activity.session_store import SQLAlchemySessionStore
from registry.loader import REGISTRY_ROOT, load_registry, read_runtime_pins
from workers.main import build_harness

PINNED = read_runtime_pins(REGISTRY_ROOT)["dsh"]


@pytest.fixture
def engine() -> AsyncEngine:
    return create_async_engine("postgresql+asyncpg://unused:unused@127.0.0.1:9/unused")


@pytest.fixture
def volume() -> Iterator[Path]:
    path = Path(tempfile.mkdtemp(prefix="dshw-", dir="/tmp"))  # short: a socket path
    yield path
    shutil.rmtree(path, ignore_errors=True)


@asynccontextmanager
async def launcher(control: Path, report: dict[str, Any]) -> AsyncIterator[list[str]]:
    """A stand-in for the DSH launcher that answers `digests`."""
    ops: list[str] = []

    async def serve(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        while line := await reader.readline():
            request = json.loads(line)
            ops.append(request["op"])
            writer.write((json.dumps({"id": request["id"], "digests": report}) + "\n").encode())
            await writer.drain()
        writer.close()

    server = await asyncio.start_unix_server(serve, str(control))
    try:
        yield ops
    finally:
        server.close()
        await server.wait_closed()


async def test_local_default_keeps_the_openai_agents_runner(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PRAXIS_SCRATCH", "/scratch-for-test")
    monkeypatch.setenv("DSH_CONTROL", "/nonexistent/.control.sock")  # never contacted
    registry = load_registry()
    acts = await build_harness(
        registry, registry.templates["local-default"], engine, MemoryBlobStore(), "worker"
    )
    assert isinstance(acts.runner, OpenAIAgentsRunner)
    assert acts.scratch == Path("/scratch-for-test") and acts.open_attempt is None
    assert acts.session_store is SQLAlchemySessionStore


async def test_local_dsh_gets_the_dsh_runner_after_the_pin_check(
    engine: AsyncEngine, volume: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    control = volume / ".control.sock"
    monkeypatch.setenv("DSH_CONTROL", str(control))
    registry = load_registry()
    async with launcher(control, {"integrity": "ok", "requirements_digest": PINNED}) as ops:
        acts = await build_harness(
            registry, registry.templates["local-dsh"], engine, MemoryBlobStore(), "worker"
        )
    assert ops == ["digests"]  # asked before serving
    assert isinstance(acts.runner, DshRunner) and acts.runner.control == control
    assert acts.open_attempt == acts.runner.open_attempt
    assert acts.scratch == volume  # attempt trees live on the shared volume


@pytest.mark.parametrize(
    "report",
    [
        {"integrity": "ok", "requirements_digest": "sha256:" + "0" * 64},
        {"integrity": "mismatch", "requirements_digest": PINNED, "mismatches": ["runtime"]},
    ],
)
async def test_local_dsh_refuses_a_launcher_that_differs_from_the_lock(
    engine: AsyncEngine, volume: Path, monkeypatch: pytest.MonkeyPatch, report: dict[str, Any]
) -> None:
    control = volume / ".control.sock"
    monkeypatch.setenv("DSH_CONTROL", str(control))
    registry = load_registry()
    async with launcher(control, report):
        with pytest.raises(CapabilityError, match="DSH runtime"):
            await build_harness(
                registry, registry.templates["local-dsh"], engine, MemoryBlobStore(), "worker"
            )


async def test_local_dsh_refuses_without_a_launcher(
    engine: AsyncEngine, volume: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSH_CONTROL", str(volume / ".control.sock"))
    registry = load_registry()
    with pytest.raises(CapabilityError, match="cannot reach the DSH launcher"):
        await build_harness(
            registry, registry.templates["local-dsh"], engine, MemoryBlobStore(), "worker"
        )
