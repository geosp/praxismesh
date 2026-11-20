"""The worker-side parts of `DshRunner`, without a DSH container: model gateway,
tool executor, session store and launcher client (DSH migration plan D1, D4, D6,
R11, R14, R16; phase 02 task 2.4)."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import stat
import tempfile
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from common.blob_store import BlobCorrupt, MemoryBlobStore
from common.persistence.repositories import Checkpoint
from common.schemas import BlobRef
from harness_activity.config import HarnessConfig
from harness_activity.dsh.composition import TOOL_PREFIX
from harness_activity.dsh.executor import Executor
from harness_activity.dsh.gateway import Gateway, SocketServer, as_stream, to_model
from harness_activity.dsh.launcher_client import LauncherClient, LauncherError
from harness_activity.dsh.ledger import DSH_MAX_OUTPUT_TOKENS, UsageLedger
from harness_activity.dsh.runner import share
from harness_activity.dsh.session import DshSessionStore
from harness_activity.events import AttemptEvents, MemorySink
from harness_activity.runner import StopRun, Superseded, Usage
from harness_activity.tools import CommandResult
from tests.support.dsh import MemoryLedgerStore

KEY = {"authorization": "Bearer attempt-key"}
GRANTED = {"read_file", "finish_task"}


def completion(tool: str | None = None, usage: dict[str, int] | None = None) -> dict[str, Any]:
    message: dict[str, Any] = {"role": "assistant", "content": "hello"}
    if tool is not None:
        call = {"id": "call-1", "type": "function", "function": {"name": tool, "arguments": "{}"}}
        message = {"role": "assistant", "content": None, "tool_calls": [call]}
    return {
        "id": "c1",
        "model": "spark",
        "choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 7, "completion_tokens": 3} if usage is None else usage,
    }


def request(*tool_results: str, tools: set[str] = GRANTED, **extra: Any) -> bytes:
    messages: list[dict[str, Any]] = [{"role": "user", "content": "secret task text"}]
    for call_id in tool_results:
        function = {"name": TOOL_PREFIX + "read_file", "arguments": "{}"}
        messages.append(
            {"role": "assistant", "tool_calls": [{"id": call_id, "function": function}]}
        )
        messages.append({"role": "tool", "tool_call_id": call_id, "content": "x"})
    body = {
        "model": "spark",
        "stream": True,
        "stream_options": {"include_usage": True},
        "messages": messages,
        "tools": [{"type": "function", "function": {"name": TOOL_PREFIX + n}} for n in tools],
        **extra,
    }
    return json.dumps(body).encode()


class Rig:
    def __init__(self, respond: Any = None, budget: int = 1000, steps: int = 8) -> None:
        self.sent: list[dict[str, Any]] = []
        self.headers: list[httpx.Headers] = []
        self.barriers: list[dict[str, Any]] = []
        self.barrier_error: Exception | None = None
        self.finished = False
        self.steps = 0
        self.refused: list[str] = []
        self.sink = MemorySink()
        self.store = MemoryLedgerStore()
        self.usage = Usage()
        self.ledger = UsageLedger(self.store, "task", 1, 1, budget, steps)

        def handler(req: httpx.Request) -> httpx.Response:
            self.sent.append(json.loads(req.content))
            self.headers.append(req.headers)
            return respond(req) if respond else httpx.Response(200, json=completion())

        async def barrier(body: dict[str, Any]) -> None:
            self.barriers.append(body)
            if self.barrier_error is not None:
                raise self.barrier_error

        def on_response() -> None:
            self.steps += 1

        self.gateway = Gateway(
            model="spark",
            base_url="http://model.test",
            api_key="worker-credential",
            attempt_key="attempt-key",
            granted=set(GRANTED),
            ledger=self.ledger,
            usage=self.usage,
            template_ref="local-dsh@1",
            finished=lambda: self.finished,
            on_response=on_response,
            refused=self.refused,
            barrier=barrier,
            events=AttemptEvents(self.sink, "wf", "task", 1, 1),
            client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )

    async def post(self, body: bytes, headers: dict[str, str] | None = None) -> tuple[int, Any]:
        status, kind, data = await self.gateway.completions(
            KEY if headers is None else headers, body
        )
        if kind == "text/event-stream":
            lines = [x[6:] for x in data.decode().split("\n\n") if x.startswith("data: {")]
            return status, [json.loads(x) for x in lines]
        return status, json.loads(data)


async def test_gateway_forwards_with_bare_names_and_settles_the_ledger() -> None:
    rig = Rig(lambda req: httpx.Response(200, json=completion("read_file")))
    status, chunks = await rig.post(request())
    assert status == 200
    # The endpoint got the worker's credential, bare tool names and no stream.
    (sent,) = rig.sent
    assert rig.headers[0]["authorization"] == "Bearer worker-credential"
    assert {t["function"]["name"] for t in sent["tools"]} == GRANTED
    assert sent["stream"] is False and "stream_options" not in sent
    # DSH got its own tool names back, as a stream that ends with the usage.
    assert chunks[0]["choices"][0]["delta"]["tool_calls"][0]["function"]["name"] == (
        TOOL_PREFIX + "read_file"
    )
    assert chunks[-1]["usage"] == {"prompt_tokens": 7, "completion_tokens": 3}
    # R11: usage is the ledger's; R16: a token event with counts only.
    assert rig.store.rows == {("task", 1, 1, "req-0001"): (7, 3)}
    assert (rig.usage.tokens_in, rig.usage.tokens_out, rig.usage.inner_turns) == (7, 3, 1)
    (event,) = rig.sink.events
    assert event.type == "token" and event.attempt_id == "task:1:1"
    assert event.payload == {"request_id": "req-0001", "input_tokens": 7, "output_tokens": 3}
    assert rig.steps == 1


async def test_gateway_rejects_another_caller() -> None:
    rig = Rig()
    assert (await rig.post(request(), {}))[0] == 403
    assert (await rig.post(request(), {"authorization": "Bearer guess"}))[0] == 403
    assert rig.sent == [] and rig.store.rows == {}


@pytest.mark.parametrize(
    "body",
    [
        request(tools=GRANTED | {"skill"}),  # a tool the template did not grant
        request(tools={"finish_task"}),  # a granted tool is missing
        request(model="another-model"),
    ],
)
async def test_gateway_blocks_a_changed_catalog_or_model(body: bytes) -> None:
    rig = Rig()
    assert (await rig.post(body))[0] == 403
    assert rig.gateway.blocked and rig.gateway.abort.is_set()
    assert rig.sent == [] and rig.store.rows == {}


async def test_barrier_runs_before_every_request_after_the_first() -> None:
    rig = Rig()
    await rig.post(request())
    assert rig.barriers == []  # D6: not before the first one
    await rig.post(request("call-1"))
    await rig.post(request("call-1", "call-2"))
    assert [b["messages"][-1]["tool_call_id"] for b in rig.barriers] == ["call-1", "call-2"]
    assert len(rig.sent) == 3


async def test_stop_run_in_the_barrier_denies_the_request_as_token_budget() -> None:
    rig = Rig()
    await rig.post(request())
    rig.barrier_error = StopRun("token budget for the task is used up")
    status, _ = await rig.post(request("call-1"))
    assert status == 429 and len(rig.sent) == 1
    assert rig.ledger.denials() == ["token budget"]
    assert rig.gateway.stop_summary == "token budget for the task is used up"


async def test_superseded_in_the_barrier_aborts_the_attempt() -> None:
    rig = Rig()
    await rig.post(request())
    rig.barrier_error = Superseded("newer attempt")
    assert (await rig.post(request("call-1")))[0] == 429
    assert rig.gateway.error_type == "Superseded" and rig.gateway.abort.is_set()


async def test_stale_attempt_dispatches_nothing() -> None:
    """D10, R11 (review F61): the ledger's fenced dispatch refuses a stale attempt,
    even on its first request, which runs no barrier; the attempt is aborted."""
    rig = Rig()
    rig.store.superseded = True
    assert (await rig.post(request()))[0] == 429
    assert rig.sent == [] and rig.store.rows == {}
    assert rig.gateway.error_type == "Superseded" and rig.gateway.abort.is_set()


async def test_failed_barrier_denies_the_request_without_dispatch() -> None:
    rig = Rig()
    await rig.post(request())
    rig.barrier_error = RuntimeError("blob store down")
    assert (await rig.post(request("call-1")))[0] == 429
    assert rig.gateway.fault == "checkpoint barrier failed" and len(rig.sent) == 1


async def test_no_request_after_finish_task() -> None:
    rig = Rig()
    rig.finished = True
    assert (await rig.post(request()))[0] == 429
    assert rig.ledger.denials() == ["explicit completion"] and rig.sent == []


async def test_step_limit_is_a_recorded_denial() -> None:
    rig = Rig(steps=1)
    await rig.post(request())
    assert (await rig.post(request("call-1")))[0] == 429
    assert rig.ledger.denials() == ["model-step limit"]


async def test_rejected_request_is_known_zero_and_bad_input() -> None:
    rig = Rig(lambda req: httpx.Response(400, json={"error": "context too long"}))
    status, body = await rig.post(request())
    assert status == 400 and "context too long" not in json.dumps(body)
    assert rig.gateway.fault == "provider rejected input"
    assert rig.store.rows == {("task", 1, 1, "req-0001"): (0, 0)}


@pytest.mark.parametrize(
    "respond",
    [
        lambda req: httpx.Response(503, text="overloaded"),
        lambda req: (_ for _ in ()).throw(httpx.ConnectError("refused")),
        lambda req: httpx.Response(200, json={**completion(), "usage": None}),
    ],
)
async def test_unobserved_usage_stays_unsettled(respond: Any) -> None:
    """D9: the row written before dispatch stays open, so the next attempt charges it."""
    rig = Rig(respond)
    assert (await rig.post(request()))[0] == 502
    assert rig.store.rows == {("task", 1, 1, "req-0001"): None}
    assert rig.ledger.settled()["unknown_usage"] == 1 and rig.gateway.fault is not None
    assert (await rig.post(request("call-1")))[0] == 429  # nothing more is dispatched


async def test_ungranted_tool_call_is_logged_and_left_unprefixed() -> None:
    rig = Rig(lambda req: httpx.Response(200, json=completion("delete_database")))
    _, chunks = await rig.post(request())
    assert chunks[0]["choices"][0]["delta"]["tool_calls"][0]["function"]["name"] == (
        "delete_database"
    )
    assert rig.refused == ["delete_database"]
    # R16 (review F91): the refused call is visible as a call and its result.
    refused = [(e.type, e.payload) for e in rig.sink.events if e.type != "token"]
    assert refused == [
        ("tool_call", {"tool": "delete_database", "call": None}),
        ("tool_result", {"tool": "delete_database", "call": None, "status": "refused"}),
    ]


@pytest.mark.parametrize("asked", [None, 100, 2048, 9000])
def test_output_is_capped_at_the_charge_assumption(asked: int | None) -> None:
    """D9 (review F73): every request the endpoint gets is bounded by the output cap
    the conservative charge assumes, whatever DSH asked for."""
    body: dict[str, Any] = {"model": "spark", "messages": []}
    if asked is not None:
        body["max_tokens"] = asked
    sent = to_model(body)
    assert sent["max_tokens"] == min(asked or DSH_MAX_OUTPUT_TOKENS, DSH_MAX_OUTPUT_TOKENS)
    assert "max_completion_tokens" not in sent


def test_request_and_response_translation() -> None:
    sent = to_model(json.loads(request("call-1")))
    assert sent["messages"][1]["tool_calls"][0]["function"]["name"] == "read_file"
    stream = as_stream(completion()).decode()
    assert stream.endswith("data: [DONE]\n\n") and '"content": "hello"' in stream


@pytest.fixture
def short_dir() -> Iterator[Path]:
    path = Path(tempfile.mkdtemp(prefix="dshu-", dir="/tmp"))  # short: socket paths
    yield path
    shutil.rmtree(path, ignore_errors=True)


async def test_socket_server_serves_one_request_per_connection(short_dir: Path) -> None:
    async def echo(headers: dict[str, str], body: bytes) -> tuple[int, str, bytes]:
        return 200, "application/json", json.dumps({"got": body.decode()}).encode()

    server = SocketServer(short_dir / "gateway.sock", {("POST", "/tool"): echo})
    await server.start()
    try:
        assert stat.S_IMODE((short_dir / "gateway.sock").stat().st_mode) == 0o660

        async def call(path: str) -> bytes:
            reader, writer = await asyncio.open_unix_connection(str(short_dir / "gateway.sock"))
            writer.write(f"POST {path} HTTP/1.1\r\nContent-Length: 2\r\n\r\nhi".encode())
            await writer.drain()
            data = await reader.read()
            writer.close()
            return data

        ok = await call("/tool")
        assert ok.startswith(b"HTTP/1.1 200") and ok.endswith(b'{"got": "hi"}')
        assert (await call("/v1/anything-else")).startswith(b"HTTP/1.1 403")
    finally:
        await server.close()
    assert not (short_dir / "gateway.sock").exists()


# -- executor ------------------------------------------------------------------------


def config(cli_tools: list[str] | None = None) -> HarnessConfig:
    return HarnessConfig(
        template_ref="local-dsh@1",
        template_hash="sha256:x",
        model="spark",
        base_url="http://model.test",
        api_key="k",
        instructions="",
        inner_max_turns=8,
        cli_tools=["wc"] if cli_tools is None else cli_tools,
        skills_bundle=None,
    )


def executor(workspace: Path, **kw: Any) -> tuple[Executor, MemorySink, list[str]]:
    sink, commands = MemorySink(), []

    def run_command(command: str) -> CommandResult:
        commands.append(command)
        return CommandResult(0, "3 file.txt\n")

    made = Executor(
        workspace, config(**kw), run_command, Usage(), AttemptEvents(sink, "wf", "task", 1, 1)
    )
    return made, sink, commands


async def test_executor_offers_the_production_catalog(tmp_path: Path) -> None:
    ex, _, _ = executor(tmp_path)
    assert ex.granted == {"read_file", "write_file", "list_files", "finish_task", "run_command"}
    assert all(set(t) == {"name", "description", "inputSchema"} for t in ex.catalog)
    no_commands, _, _ = executor(tmp_path, cli_tools=[])
    assert "run_command" not in no_commands.granted  # only with granted cli_tools


async def test_executor_runs_bodies_and_emits_content_free_events(tmp_path: Path) -> None:
    ex, sink, commands = executor(tmp_path)
    written: list[Path] = []
    ex.after_write = written.append
    text, error = await ex.call("write_file", {"path": "a.txt", "content": "top secret"})
    assert (text, error) == ("wrote 10 characters to a.txt", False)
    assert (tmp_path / "a.txt").read_text() == "top secret" and written == [tmp_path / "a.txt"]
    assert (await ex.call("read_file", {"path": "a.txt"}))[0] == "top secret"
    assert "exit=0" in (await ex.call("run_command", {"command": "wc -l a.txt"}))[0]
    assert commands == ["wc -l a.txt"]  # through the launcher's CommandRunner
    assert "refused" in (await ex.call("run_command", {"command": "curl x"}))[0]
    assert ex.usage.tool_calls == 4
    assert [(e.type, e.payload["tool"]) for e in sink.events[:2]] == [
        ("tool_call", "write_file"),
        ("tool_result", "write_file"),
    ]
    assert [e.payload.get("status") for e in sink.events if e.type == "tool_result"] == [
        "ok",
        "ok",
        "ok",
        "error",
    ]
    assert "top secret" not in json.dumps([e.payload for e in sink.events])  # R16
    assert [e["outcome"] for e in ex.entries] == ["ok", "ok", "ok", "error"]


async def test_executor_refuses_what_was_not_granted(tmp_path: Path) -> None:
    ex, sink, _ = executor(tmp_path)
    text, error = await ex.call("delete_database", {})
    assert error and text.startswith("refused") and ex.usage.tool_calls == 0
    assert ex.state.refused == ["delete_database"]
    assert [(e.type, e.payload) for e in sink.events] == [  # paired (review F91)
        ("tool_call", {"tool": "delete_database", "call": 1}),
        ("tool_result", {"tool": "delete_database", "call": 1, "status": "refused"}),
    ]
    assert (await ex.call("read_file", {"path": "a", "extra": 1}))[1]  # unknown argument


async def test_finish_task_ends_the_run_and_tracks_failed_siblings(tmp_path: Path) -> None:
    ex, _, _ = executor(tmp_path)
    assert (await ex.call("read_file", {"path": "missing.txt"}))[0].startswith("error")
    assert ex.state.failed_in_step == ["read_file"]
    bad = await ex.call("finish_task", {"status": "maybe", "summary": "x"})
    # Invalid arguments: the production wrapper's own error, and no finish (R18).
    assert not ex.finished and ex.state.finish is None and bad[0].startswith("An error occurred")
    await ex.call("finish_task", {"status": "done", "summary": "ok"})
    assert ex.finished and ex.state.finish is not None and ex.state.finish.status == "done"
    assert ex.state.failed_in_step == ["read_file"]  # the runner turns this into `continue`
    again, error = await ex.call("read_file", {"path": "a"})
    assert error and "already finished" in again
    ex.new_step()
    assert ex.state.failed_in_step == []


# -- session store, permissions, launcher client ---------------------------------------


def checkpoint(session_ref: BlobRef | None, digest: str | None) -> Checkpoint:
    ref = BlobRef(
        id="r",
        key="k",
        checksum="sha256:" + "0" * 64,
        content_type="x",
        bytes=0,
        retention_class="task",
        created_at=datetime.now(UTC),
    )
    return Checkpoint("c", "t", 1, 1, 0, "t", 0, ref, None, session_ref, digest)


async def test_session_store_round_trips_the_session_blob(tmp_path: Path) -> None:
    blobs = MemoryBlobStore()
    first = DshSessionStore("task", tmp_path / "a", blobs)
    await first.load(None)
    (tmp_path / "a/sessions").mkdir()
    (tmp_path / "a/sessions/session.jsonl").write_text('{"id": "call-1"}\n')
    snapshot = await first.capture()
    assert snapshot.position == 0 and snapshot.session_ref is not None  # D1
    assert snapshot.session_digest is not None
    assert snapshot.session_ref.retention_class == "transcript"  # `task` reads as transcript

    second = DshSessionStore("task", tmp_path / "b", blobs)
    (tmp_path / "b").mkdir()
    (tmp_path / "b/stale").write_text("from a lost attempt")
    await second.load(checkpoint(snapshot.session_ref, snapshot.session_digest))
    assert sorted(p.name for p in (tmp_path / "b").rglob("*")) == ["session.jsonl", "sessions"]
    assert (await second.capture()).session_digest == snapshot.session_digest
    assert await second.session.get_items() == []

    with pytest.raises(BlobCorrupt):
        await second.load(checkpoint(snapshot.session_ref, "sha256:" + "f" * 64))
    await second.load(None)
    assert list((tmp_path / "b").iterdir()) == []
    await second.load(replace(checkpoint(None, None)))  # an openai_agents checkpoint
    assert list((tmp_path / "b").iterdir()) == []


def test_share_never_follows_a_link_out_of_the_tree(tmp_path: Path) -> None:
    """Review F97: a command may plant links in the tree; share changes only what
    is inside it."""
    outside = tmp_path / "outside"
    outside.mkdir(mode=0o700)
    (outside / "secret").write_text("x")
    (outside / "secret").chmod(0o600)
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "file-link").symlink_to(outside / "secret")
    (tree / "dir-link").symlink_to(outside, target_is_directory=True)
    share(tree, os.getgid())
    assert stat.S_IMODE((outside / "secret").stat().st_mode) == 0o600
    assert stat.S_IMODE(outside.stat().st_mode) == 0o700


def test_file_bodies_never_follow_a_link(tmp_path: Path) -> None:
    """Review F97: reads and writes refuse any link component, even inside."""
    from harness_activity import tools

    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret").write_text("TOP")
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "dir-link").symlink_to(outside, target_is_directory=True)
    (ws / "file-link").symlink_to(outside / "secret")
    assert tools.read_file_body(ws, "dir-link/secret").startswith("error")
    assert tools.read_file_body(ws, "file-link").startswith("error")
    assert tools.write_file_body(ws, "dir-link/new", "x").startswith("error")
    assert tools.write_file_body(ws, "file-link", "x").startswith("error")
    assert (outside / "secret").read_text() == "TOP" and not (outside / "new").exists()
    assert tools.write_file_body(ws, "a/b/c.txt", "ok").startswith("wrote")
    assert tools.read_file_body(ws, "a/b/c.txt") == "ok"
    with pytest.raises(tools.WorkspaceError):
        tools.read_regular(ws, "dir-link/secret")


def test_list_files_never_follows_a_link(tmp_path: Path) -> None:
    """Review F140: listing a linked directory, or a tree holding one, shows
    nothing outside the workspace."""
    from harness_activity import tools

    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "worker-secret").write_text("x")
    ws = tmp_path / "ws"
    (ws / "sub").mkdir(parents=True)
    (ws / "sub/kept.txt").write_text("ok")
    (ws / "dir-link").symlink_to(outside, target_is_directory=True)
    (ws / "sub/inner-link").symlink_to(outside, target_is_directory=True)
    assert str(tools.list_files_body(ws, "dir-link")).startswith("error")
    assert tools.list_files_body(ws, ".") == ["sub/kept.txt"]
    assert tools.list_files_body(ws, "sub") == ["sub/kept.txt"]


def test_launcher_destroy_error_marks_the_attempt_dirty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R10 (review F143): a cleanup that raises still reports the attempt dirty."""
    import importlib.util
    import sys

    path = Path(__file__).resolve().parents[1] / "infra/dsh/launcher.py"
    monkeypatch.syspath_prepend(str(path.parent))
    spec = importlib.util.spec_from_file_location("dsh_launcher_under_test", path)
    assert spec is not None and spec.loader is not None
    launcher = importlib.util.module_from_spec(spec)
    sys.modules.pop("dsh_launcher_under_test", None)
    spec.loader.exec_module(launcher)
    cgroup = tmp_path / "cg"
    (cgroup / "cgroup.kill").mkdir(parents=True)  # writing it raises an OSError
    (cgroup / "cgroup.freeze").write_text("0")
    monkeypatch.setattr(launcher, "_cgroup_of", lambda attempt: cgroup)
    monkeypatch.setattr(launcher, "ATTEMPTS", tmp_path / "attempts")
    report = launcher.destroy("task-x/1/1")
    assert report["processes_left"] is None and report["tree_removed"] is False
    assert {"task-x/1/1"} == launcher.DIRTY


def test_share_gives_the_group_the_owners_access(tmp_path: Path) -> None:
    (tmp_path / "dir").mkdir(mode=0o755)
    (tmp_path / "dir/file").write_text("x")
    (tmp_path / "dir/file").chmod(0o644)
    (tmp_path / "dir/read-only").write_text("skill")
    (tmp_path / "dir/read-only").chmod(0o444)
    share(tmp_path / "dir", os.getgid())

    def mode(name: str) -> int:
        return stat.S_IMODE((tmp_path / name).stat().st_mode)

    assert mode("dir") == 0o2775 and mode("dir/file") == 0o664
    assert mode("dir/read-only") == 0o444


async def test_launcher_client_matches_replies_by_id(short_dir: Path) -> None:
    """`exec` runs beside the connection: its reply may come after a later request's."""

    async def serve(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        held: dict[str, Any] | None = None
        while line := await reader.readline():
            req = json.loads(line)
            if req["op"] == "exec":
                held = {"id": req["id"], "exit": 0, "stdout": "slow"}
                continue
            reply = {"error": "ValueError", "detail": "no"} if req["op"] == "bad" else {"ok": True}
            writer.write((json.dumps({"id": req["id"], **reply}) + "\n").encode())
            if held is not None:
                writer.write((json.dumps(held) + "\n").encode())
                held = None
            await writer.drain()
        writer.close()

    server = await asyncio.start_unix_server(serve, str(short_dir / "c.sock"))
    client = await LauncherClient.connect(short_dir / "c.sock")
    try:
        slow = asyncio.create_task(client.request("exec", command="sleep 1"))
        await asyncio.sleep(0.05)
        assert await client.request("freeze") == {"ok": True}  # not delayed by the exec
        assert (await slow)["stdout"] == "slow"
        with pytest.raises(LauncherError, match="ValueError"):
            await client.request("bad")
    finally:
        await client.close()
        server.close()
        await server.wait_closed()
    with pytest.raises(LauncherError):
        await LauncherClient.connect(short_dir / "missing.sock")
