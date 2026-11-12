"""Recovery on another worker, and no repeated side effects (spec execution/durability;
RFC: Recovery check). Workers run as host processes; a test SIGKILLs the one that
holds the attempt, at a point the fake model or the sample server holds open.

    make recovery-check
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from common.blob_store.s3 import S3BlobStore
from common.persistence.repositories import RecordingBlobStore, make_engine
from common.schemas import TaskResult
from orchestrator.submit import prepare_task, start_task
from registry.loader import load_registry
from tests.support.fake_model import FakeModel
from tests.support.worker_procs import WorkerProcs, make_test_registry, worker_processes
from workers.main import connect

pytestmark = pytest.mark.integration
INSTRUCTIONS = "Recovery check: follow the steps."


async def query(sql: str, **params: Any) -> list[Any]:
    engine = make_engine()
    try:
        async with engine.connect() as conn:
            return list((await conn.execute(text(sql), params)).all())
    finally:
        await engine.dispose()


async def wait_for(check: Any, what: str, timeout: float = 60) -> None:
    for _ in range(int(timeout * 4)):
        if await check():
            return
        await asyncio.sleep(0.25)
    raise AssertionError(f"timed out waiting for {what}")


@pytest.fixture
def recovery_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[Path, Path]]:
    pause = tmp_path / "pause"
    registry = make_test_registry(tmp_path / "registry", pause)
    yield registry, pause


async def submit(registry: Path, outputs: list[str], env: dict[str, str]) -> tuple[str, Any]:
    engine = make_engine()
    s3 = S3BlobStore.from_env()
    await s3.ensure_bucket()
    start = await prepare_task(
        {"profile": "default", "instructions": INSTRUCTIONS, "outputs": outputs},
        load_registry(registry),
        RecordingBlobStore(s3, engine),
        base_dir=Path.cwd(),
    )
    await engine.dispose()
    return start.task_id, await start_task(await connect("praxis-test"), start)


async def holder(workers: WorkerProcs, task_id: str) -> str:
    rows = await query(
        "SELECT worker_identity FROM task_attempts WHERE task_id = :t ORDER BY attempt DESC",
        t=task_id,
    )
    return workers.name_of(workers.pid_of(rows[0][0]))


def tool_messages(request: dict[str, Any]) -> list[str]:
    """Tool results as text; MCP results arrive as a list of content parts."""
    texts = []
    for m in request["messages"]:
        if m["role"] != "tool":
            continue
        content = m["content"]
        if isinstance(content, list):
            content = "".join(part.get("text", "") for part in content)
        texts.append(str(content))
    return texts


async def test_recovery_after_workspace_edits(
    tmp_path: Path, recovery_env: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    registry, _ = recovery_env
    steps: list[dict[str, Any]] = [
        {"tool": "write_file", "args": {"path": "notes.txt", "content": "first edit\n"}},
        {"tool": "lookup_price", "args": {"sku": "SKU-1"}, "pause": True},
        {"tool": "write_file", "args": {"path": "final.md", "content": "finished\n"}},
        {"tool": "finish_task", "args": {"status": "done", "summary": "Recovered."}},
    ]
    with (
        FakeModel(steps) as fake,
        worker_processes(tmp_path / "scratch", fake.base_url, registry) as workers,
    ):
        monkeypatch.setenv("PRAXIS_QUEUE_PREFIX", workers.env["PRAXIS_QUEUE_PREFIX"])
        task_id, handle = await submit(registry, ["notes.txt", "final.md"], workers.env)

        async def paused_after_checkpoint() -> bool:
            rows = await query(
                "SELECT count(*) FROM checkpoints WHERE task_id = :t AND seq >= 1", t=task_id
            )
            return fake.state.paused_step == 1 and rows[0][0] > 0

        await wait_for(paused_after_checkpoint, "the pause after an acknowledged checkpoint")
        lost = await holder(workers, task_id)
        before_kill = len(fake.state.requests)
        workers.kill(lost)
        fake.state.release.set()
        result = TaskResult.model_validate(await asyncio.wait_for(handle.result(), 120))

    assert result.status == "succeeded" and result.turns == 1 and result.attempts == 2
    s3 = S3BlobStore.from_env()
    files = {a.path: (await s3.get(a.ref)).decode() for a in result.artifacts}
    assert files == {"notes.txt": "first edit\n", "final.md": "finished\n"}
    attempts = await query(
        "SELECT attempt, outcome, worker_identity FROM task_attempts WHERE task_id = :t "
        "ORDER BY attempt",
        t=task_id,
    )
    assert [(a, o) for a, o, _ in attempts] == [(1, "lost"), (2, "done")]
    assert workers.name_of(workers.pid_of(attempts[1][2])) != lost
    # The resumed attempt sent the conversation so far: the instructions and the
    # first edit's tool call and result, not a fresh start (J15).
    resumed = fake.state.requests[before_kill]
    contents = json.dumps(resumed["messages"])
    assert INSTRUCTIONS in contents and "first edit" in contents
    assert any("wrote" in m for m in tool_messages(resumed))


async def test_side_effect_not_repeated_after_crash(
    tmp_path: Path, recovery_env: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    registry, pause = recovery_env
    steps = [
        {"tool": "record_order", "args": {"sku": "SKU-2", "qty": 4}},
        {"tool": "finish_task", "args": {"status": "done", "summary": "Ordered once."}},
    ]
    with (
        FakeModel(steps) as fake,
        worker_processes(tmp_path / "scratch", fake.base_url, registry) as workers,
    ):
        monkeypatch.setenv("PRAXIS_QUEUE_PREFIX", workers.env["PRAXIS_QUEUE_PREFIX"])
        task_id, handle = await submit(registry, [], workers.env)

        async def effect_committed_and_held() -> bool:
            return Path(f"{pause}.paused").exists()

        await wait_for(effect_committed_and_held, "record_order to commit and hold")
        workers.kill(await holder(workers, task_id))
        Path(f"{pause}.release").touch()
        result = TaskResult.model_validate(await asyncio.wait_for(handle.result(), 120))

    assert result.status == "succeeded" and result.attempts == 2
    orders = await query("SELECT count(*) FROM sample_orders WHERE task_id = :t", t=task_id)
    assert orders[0][0] == 1
    # The resumed attempt called record_order again and got the recorded result.
    results = [json.loads(m) for r in fake.state.requests for m in tool_messages(r)]
    assert any(r.get("repeated") is True and r["sku"] == "SKU-2" for r in results)


async def test_checkpoint_matches_session_position(
    tmp_path: Path, recovery_env: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """seq 0 is taken before the first model call and holds the instructions; each
    later checkpoint's position matches the session after the previous step (J15)."""
    registry, _ = recovery_env
    steps = [
        {"tool": "write_file", "args": {"path": "a.txt", "content": "a"}},
        {"tool": "finish_task", "args": {"status": "done", "summary": "ok"}},
    ]
    with (
        FakeModel(steps) as fake,
        worker_processes(tmp_path / "scratch", fake.base_url, registry) as workers,
    ):
        monkeypatch.setenv("PRAXIS_QUEUE_PREFIX", workers.env["PRAXIS_QUEUE_PREFIX"])
        task_id, handle = await submit(registry, [], workers.env)
        await asyncio.wait_for(handle.result(), 120)
    positions = await query(
        "SELECT seq, session_position FROM checkpoints WHERE task_id = :t ORDER BY seq",
        t=task_id,
    )
    # seq 0: the instructions; seq 1: + the write_file call and its result;
    # seq 2 (final): + the finish_task call and its result.
    assert positions == [(0, 1), (1, 3), (2, 5)]
    first = fake.state.requests[0]
    assert first["messages"][-1] == {"role": "user", "content": INSTRUCTIONS}
