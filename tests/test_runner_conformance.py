"""`HarnessRunner` conformance against the deterministic fake model, with the real
sample MCP server as a subprocess (spec execution/harness-turn; RFC Testing).

Runs in the unit suite for `openai_agents`: no stack needed (read-only MCP tools
only). The `dsh` runs are marked `integration`: they start a DSH container."""

from __future__ import annotations

import json
import logging
import os
import shutil
import sys
from collections.abc import AsyncIterator, Callable, Iterator
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml

from common.observability import disable_sdk_tracing
from harness_activity.config import HarnessConfig, McpConfig, build_config
from harness_activity.events import AttemptEvents, MemorySink
from harness_activity.runner import HarnessRunner, OpenAIAgentsRunner, Usage
from harness_activity.session_store import SessionStore
from registry.loader import REGISTRY_ROOT, load_registry
from tests.support.dsh import DshContainer, build_image, start_container
from tests.support.events import attempt_events
from tests.support.fake_model import FakeModel
from tests.support.session_stores import MemorySessionStore, store_contract


def script(*steps: dict[str, Any]) -> list[dict[str, Any]]:
    return list(steps)


# Every runner must pass this suite (plan 2026-11-15-dsh-production-harness, R3).
# `dsh` needs Docker for its DSH container, so its runs are integration tests.
RUNNERS: dict[str, Callable[[], HarnessRunner]] = {"openai_agents": OpenAIAgentsRunner}
make_runner: Callable[[], HarnessRunner] = OpenAIAgentsRunner
# The runner's session comes from a session store, as in run_harness_turn (D1).
# The production SQLAlchemySessionStore is checked against Postgres in
# tests/integration/test_harness_activity.py::test_session_store_contract.
make_store: Callable[[str], SessionStore] = MemorySessionStore
runner_name = "openai_agents"  # which runner this test runs, set by `_runner`


def _subdir(base: Path, name: str) -> Path:
    path = base / name
    path.mkdir()
    return path


# A new, empty workspace beside the test's own (`tmp_path`).
make_workspace: Callable[[Path, str], Path] = _subdir
# Where a command finds itself: the workspace, or the DSH container's view of it.
command_cwd: Callable[[Path], str] = str


@pytest.fixture(scope="module")
def dsh_container() -> Iterator[DshContainer]:
    container = start_container(build_image())
    try:
        yield container
    finally:
        container.stop()


@pytest.fixture(
    params=[*sorted(RUNNERS), pytest.param("dsh", marks=pytest.mark.integration)], autouse=True
)
async def _runner(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[str]:
    name: str = request.param
    monkeypatch.setitem(globals(), "runner_name", name)
    if name != "dsh":
        monkeypatch.setitem(globals(), "make_runner", RUNNERS[name])
        yield name
        return
    # One DshRunner per test: it keeps each attempt (and so its workspace) until
    # the test has read the results.
    container: DshContainer = request.getfixturevalue("dsh_container")
    runner = container.runner()
    monkeypatch.setitem(globals(), "make_runner", lambda: runner)
    monkeypatch.setitem(globals(), "make_workspace", lambda base, name: container.workspace())
    monkeypatch.setitem(globals(), "command_cwd", lambda workspace: "/work")
    try:
        yield name
    finally:
        await runner.close()
        assert container.attempt_cgroups() == []  # nothing of the attempt is left


@pytest.fixture
def tmp_path(tmp_path: Path, _runner: str, request: pytest.FixtureRequest) -> Path:
    """The workspace: for `dsh`, a directory in an attempt tree on the volume the
    DSH container shares."""
    if _runner != "dsh":
        return tmp_path
    container: DshContainer = request.getfixturevalue("dsh_container")
    return container.workspace()


def instructions_seen(first_request: dict[str, Any]) -> str:
    """The template's instructions as the model got them: the system message for
    `openai_agents`, as before phase 02 (review F93); for `dsh`, the first user
    message (DSH keeps its own system message)."""
    messages = first_request["messages"]
    if runner_name != "dsh":
        assert messages[0]["role"] == "system"
        return str(messages[0]["content"])
    assert messages[1]["role"] == "user"
    return str(messages[1]["content"])


async def test_memory_store_contract() -> None:
    await store_contract(MemorySessionStore("contract"))


@pytest.fixture(autouse=True)
def _no_sdk_tracing() -> None:
    disable_sdk_tracing()


def config_for(fake: FakeModel, monkeypatch: pytest.MonkeyPatch) -> HarnessConfig:
    monkeypatch.setenv("VLLM_BASE_URL", fake.base_url)
    registry = load_registry()
    _, loaded = registry.resolve("openai")
    return build_config(registry, loaded, "task-conformance-0001")


async def no_op(usage: Usage) -> None:
    return None


async def run(
    steps: list[dict[str, Any]], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Any, FakeModel]:
    with FakeModel(steps) as fake:
        result = await make_runner().run(
            config_for(fake, monkeypatch),
            tmp_path,
            make_store("conformance").session,
            "Write the order summary.",
            no_op,
            Usage(),
            attempt_events(),
        )
        return result, fake


async def test_runner_conformance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result, fake = await run(
        script(
            {"tool": "lookup_price", "args": {"sku": "SKU-1"}},
            {
                "tool": "write_file",
                "args": {"path": "order-summary.md", "content": "Total: 37.50\n"},
            },
            {"tool": "finish_task", "args": {"status": "done", "summary": "Wrote the summary."}},
        ),
        tmp_path,
        monkeypatch,
    )
    assert result.status == "done" and result.summary == "Wrote the summary."
    assert (tmp_path / "order-summary.md").read_text() == "Total: 37.50\n"
    assert result.usage.tool_calls == 3 and result.usage.inner_turns == 3
    assert result.usage.tokens_in == 300 and result.usage.tokens_out == 30
    first = fake.state.requests[0]
    names = {t["function"]["name"] for t in first["tools"]}
    assert names == {
        "read_file",
        "write_file",
        "list_files",
        "finish_task",
        "run_command",
        "lookup_price",
        "lookup_stock",
        "get_discount",
        "get_setting",
        "record_order",
        "send_to_agent",
        "ask_agent",
        "post_status",
        "get_task_context",
    }
    system = instructions_seen(first)
    assert "finish_task" in system and ".skills/order-desk/SKILL.md" in system
    assert "response_format" not in first  # see decision log: no output_type


async def test_prohibited_tool_returns_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, fake = await run(
        script(
            {"tool": "delete_database", "args": {}},
            {"tool": "run_command", "args": {"command": "curl http://example.com"}},
            {"tool": "finish_task", "args": {"status": "done", "summary": "ok"}},
        ),
        tmp_path,
        monkeypatch,
    )
    assert result.status == "done"  # the refusals did not end or fail the turn
    tool_messages = [m for m in fake.state.requests[-1]["messages"] if m["role"] == "tool"]
    assert "delete_database" in tool_messages[0]["content"]
    assert "refused" in tool_messages[1]["content"]


async def test_inner_turn_limit_is_continue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, _ = await run(script({"tool": "list_files", "args": {}}), tmp_path, monkeypatch)
    assert result.status == "continue" and result.usage.inner_turns == 8


async def test_needs_input(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result, _ = await run(
        script(
            {
                "tool": "finish_task",
                "args": {"status": "needs_input", "summary": "?", "questions": ["Which SKU?"]},
            }
        ),
        tmp_path,
        monkeypatch,
    )
    assert result.status == "needs_input" and result.questions == ["Which SKU?"]


async def test_waiting(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Phase 2 messaging task 1.2: `finish_task("waiting")` ends the run as waiting."""
    result, _ = await run(
        script({"tool": "finish_task", "args": {"status": "waiting", "summary": "asked B"}}),
        tmp_path,
        monkeypatch,
    )
    assert result.status == "waiting" and result.summary == "asked B"


async def test_invalid_finish_arguments_continue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, _ = await run(
        script({"tool": "finish_task", "args": {"status": "maybe", "summary": "x"}}),
        tmp_path,
        monkeypatch,
    )
    assert result.status == "continue"


async def test_command_env_has_no_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CANARY_SECRET", "do-not-leak")
    _, fake = await run(
        script(
            {"tool": "run_command", "args": {"command": "sh -c env"}},
            {"tool": "finish_task", "args": {"status": "done", "summary": "ok"}},
        ),
        tmp_path,
        monkeypatch,
    )
    tool_results = (m for m in fake.state.requests[-1]["messages"] if m["role"] == "tool")
    output = next(tool_results)["content"]
    assert "exit=0" in output and "do-not-leak" not in output and "S3_SECRET" not in output
    assert os.environ["CANARY_SECRET"] == "do-not-leak"


async def test_command_runs_in_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, fake = await run(
        script(
            {"tool": "run_command", "args": {"command": "sh -c pwd"}},
            {"tool": "finish_task", "args": {"status": "done", "summary": "ok"}},
        ),
        tmp_path,
        monkeypatch,
    )
    assert f"stdout:\n{command_cwd(tmp_path)}\n" in tool_results(fake)[0]


async def test_command_timeout_is_enforced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("harness_activity.tools.COMMAND_TIMEOUT_S", 0.01)
    _, fake = await run(
        script(
            {"tool": "run_command", "args": {"command": "sh -c 'sleep 1'"}},
            {"tool": "finish_task", "args": {"status": "done", "summary": "ok"}},
        ),
        tmp_path,
        monkeypatch,
    )
    assert "did not finish within 0.01 s" in tool_results(fake)[0]


async def test_command_output_is_capped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("harness_activity.tools.OUTPUT_CAP", 20)
    _, fake = await run(
        script(
            {
                "tool": "run_command",
                "args": {"command": "sh -c 'printf abcdefghijklmnopqrstuvwxyz'"},
            },
            {"tool": "finish_task", "args": {"status": "done", "summary": "ok"}},
        ),
        tmp_path,
        monkeypatch,
    )
    output = tool_results(fake)[0]
    assert "ghijklmnopqrstuvwxyz" in output and "abcdef" not in output


async def test_finish_with_failed_sibling_is_continue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, _ = await run(
        script(
            {
                "tools": [
                    {"tool": "read_file", "args": {"path": "missing.txt"}},
                    {"tool": "finish_task", "args": {"status": "done", "summary": "done"}},
                ]
            }
        ),
        tmp_path,
        monkeypatch,
    )
    assert result.status == "continue" and "read_file" in result.summary


async def test_finish_with_successful_sibling_is_done(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, _ = await run(
        script(
            {
                "tools": [
                    {"tool": "write_file", "args": {"path": "a.txt", "content": "x"}},
                    {"tool": "finish_task", "args": {"status": "done", "summary": "done"}},
                ]
            }
        ),
        tmp_path,
        monkeypatch,
    )
    assert result.status == "done"


async def test_stop_run_and_superseded_reach_the_runner_unwrapped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The SDK must let our control signals out of `on_llm_start` (review F6e)."""
    from harness_activity.runner import StopRun, Superseded

    steps = script({"tool": "list_files", "args": {}})

    async def stop_on_second_call(usage: Usage) -> None:
        if usage.inner_turns == 1:
            raise StopRun("budget")

    with FakeModel(steps) as fake:
        config = config_for(fake, monkeypatch)
        result = await make_runner().run(
            config,
            tmp_path,
            make_store("stop").session,
            "go",
            stop_on_second_call,
            Usage(),
            attempt_events(),
        )
        assert result.status == "continue" and result.summary == "budget"
        assert len(fake.state.requests) == 1

        async def superseded(usage: Usage) -> None:
            raise Superseded("newer attempt")

        with pytest.raises(Superseded):
            await make_runner().run(
                config,
                tmp_path,
                make_store("sup").session,
                "go",
                superseded,
                Usage(),
                attempt_events(),
            )


def tool_results(fake: FakeModel) -> list[str]:
    texts = []
    for m in fake.state.requests[-1]["messages"]:
        if m["role"] == "tool":
            c = m["content"]
            texts.append("".join(p.get("text", "") for p in c) if isinstance(c, list) else c)
    return texts


async def test_refusals_are_logged_with_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Both kinds of refusal write a log line carrying the task and attempt IDs
    (capability-model spec; threat model C4; gate F4)."""
    from common.observability import log_context
    from common.observability.logging import JsonFormatter

    caplog.set_level(logging.WARNING, logger="praxis.harness")
    with log_context(task_id="task-log-00000001", attempt=2):
        await run(
            script(
                {"tool": "delete_database", "args": {}},
                {"tool": "run_command", "args": {"command": "curl http://example.com"}},
                {"tool": "finish_task", "args": {"status": "done", "summary": "ok"}},
            ),
            tmp_path,
            monkeypatch,
        )
        lines = [json.loads(JsonFormatter().format(r)) for r in caplog.records]
    refusals = {line["msg"]: line for line in lines if line["msg"].startswith("refused")}
    assert refusals["refused tool call"]["tool"] == "delete_database"
    assert refusals["refused command"]["program"] == "curl"
    assert all(
        line["task_id"] == "task-log-00000001" and line["attempt"] == 2
        for line in refusals.values()
    )


async def test_mcp_tools_allowed_filter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An MCP tool missing from the catalog entry's `tools_allowed` is neither
    offered nor callable (gate F5)."""
    registry_dir = tmp_path / "registry"
    shutil.copytree(
        REGISTRY_ROOT, registry_dir, ignore=shutil.ignore_patterns("*.py", "__pycache__")
    )
    entry = registry_dir / "mcp" / "sample-shop.yaml"
    data = yaml.safe_load(entry.read_text())
    data["tools_allowed"] = [t for t in data["tools_allowed"] if t != "record_order"]
    entry.write_text(yaml.safe_dump(data))
    registry = load_registry(registry_dir, check_lock=False)
    with FakeModel(
        script(
            {"tool": "record_order", "args": {"sku": "SKU-1", "qty": 1}},
            {"tool": "finish_task", "args": {"status": "done", "summary": "ok"}},
        )
    ) as fake:
        monkeypatch.setenv("VLLM_BASE_URL", fake.base_url)
        _, loaded = registry.resolve("openai")
        config = build_config(registry, loaded, "task-filter-0001")
        workspace = make_workspace(tmp_path, "ws")
        await make_runner().run(
            config, workspace, make_store("filter").session, "go", no_op, Usage(), attempt_events()
        )
        offered = {t["function"]["name"] for t in fake.state.requests[0]["tools"]}
        assert "record_order" not in offered and "lookup_price" in offered
        assert "record_order" in tool_results(fake)[0]  # an error naming the tool


async def test_file_tools_stay_in_the_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`..`, absolute paths and symlinks cannot reach outside the workspace
    (threat model C6; gate F9)."""
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP-SECRET-CONTENT")
    workspace = make_workspace(tmp_path, "ws")
    (workspace / "link.txt").symlink_to(secret)
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    (outside_dir / "nested-secret.txt").write_text("NESTED-TOP-SECRET")
    (workspace / "linkdir").symlink_to(outside_dir, target_is_directory=True)
    escape = tmp_path / "escaped.txt"
    _, fake = await run(
        script(
            {"tool": "read_file", "args": {"path": "../secret.txt"}},
            {"tool": "read_file", "args": {"path": str(secret)}},
            {"tool": "read_file", "args": {"path": "link.txt"}},
            {"tool": "write_file", "args": {"path": str(escape), "content": "x"}},
            {"tool": "list_files", "args": {"path": ".."}},
            {"tool": "list_files", "args": {"path": str(outside_dir)}},
            {"tool": "list_files", "args": {"path": "linkdir"}},
            {"tool": "finish_task", "args": {"status": "done", "summary": "ok"}},
        ),
        workspace,
        monkeypatch,
    )
    results = tool_results(fake)
    assert len(results) == 7
    assert all("TOP-SECRET" not in r for r in results)
    assert all(r.startswith("error: path outside the workspace") for r in results), results
    assert not escape.exists()


def test_mcp_server_env_is_exactly_what_is_granted(monkeypatch: pytest.MonkeyPatch) -> None:
    """The config grants only its declared values; the SDK adds its documented
    platform allow-list when it creates the subprocess (threat model C7; F9)."""
    monkeypatch.setenv("VLLM_BASE_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("PRAXIS_SAMPLE_DB_URL", "postgresql+asyncpg://granted")
    monkeypatch.setenv("S3_SECRET_KEY", "not-granted")
    monkeypatch.setenv("CANARY_SECRET", "not-granted")
    registry = load_registry()
    _, loaded = registry.resolve("openai")
    servers = {
        s.name: s
        for s in build_config(
            registry, loaded, "task-env-00000001", turn=3, attempt=2,
            max_ask_wait=timedelta(minutes=2),
        ).mcp
    }  # fmt: skip
    server = servers["sample-shop"]
    # Each server gets only its own grant: comms_mcp its database URL, not the shop's.
    assert "PRAXIS_COMMS_DB_URL" in servers["comms"].env
    assert "PRAXIS_SAMPLE_DB_URL" not in servers["comms"].env
    assert set(server.env) == {
        "PATH", "LANG", "PRAXIS_TASK_ID", "PRAXIS_TURN", "PRAXIS_ATTEMPT", "PRAXIS_MAX_ASK_WAIT",
        "PRAXIS_SAMPLE_DB_URL",
    }  # fmt: skip
    assert server.env["PRAXIS_TASK_ID"] == "task-env-00000001"
    # The attempt's identity for comms_mcp (Phase 2 messaging D9) and its ask cap (D14).
    assert (server.env["PRAXIS_TURN"], server.env["PRAXIS_ATTEMPT"]) == ("3", "2")
    assert server.env["PRAXIS_MAX_ASK_WAIT"] == "120"
    assert server.env["PRAXIS_SAMPLE_DB_URL"] == "postgresql+asyncpg://granted"


def test_worker_set_variables_win_over_a_catalog_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Even an entry that slipped past the loader (#89) cannot replace the attempt's
    identity: the worker-set variables are applied after env and secret_env."""
    monkeypatch.setenv("VLLM_BASE_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("PRAXIS_TASK_ID", "task-forged-0000001")
    registry = load_registry()
    _, loaded = registry.resolve("openai")
    comms = registry.mcp_servers["comms"]
    forged = comms.model_construct(  # skips the validator, as a bypass would
        **{
            **dict(comms),
            "env": {"PRAXIS_TURN": "99"},
            "secret_env": [*comms.secret_env, "PRAXIS_TASK_ID"],
        }
    )
    monkeypatch.setitem(registry.mcp_servers, "comms", forged)
    config = build_config(registry, loaded, "task-env-00000002", turn=3, attempt=2)
    server = next(s for s in config.mcp if s.name == "comms")
    assert (server.env["PRAXIS_TASK_ID"], server.env["PRAXIS_TURN"]) == ("task-env-00000002", "3")


async def test_mcp_subprocess_env_is_granted_plus_sdk_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exercise the runner hand-off and inspect the environment in the actual
    stdio child. A worker canary must not cross that boundary (gate M6)."""
    from mcp.client.stdio import get_default_environment

    monkeypatch.setenv("CANARY_SECRET", "must-not-reach-mcp")
    with FakeModel(
        script(
            {"tool": "environment", "args": {}},
            {"tool": "finish_task", "args": {"status": "done", "summary": "ok"}},
        )
    ) as fake:
        config = config_for(fake, monkeypatch)
        granted = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "LANG": "C.UTF-8",
            "PRAXIS_TASK_ID": "task-env-process-0001",
        }
        env_server = McpConfig(
            name="environment",
            command=sys.executable,
            args=["-m", "tests.support.env_mcp"],
            env=granted,
            tools_allowed=["environment"],
            timeout_s=5,
        )
        config = replace(config, mcp=[env_server])
        await make_runner().run(
            config,
            tmp_path,
            make_store("env-process").session,
            "Report the environment.",
            no_op,
            Usage(),
            attempt_events(),
        )
        observed = json.loads(tool_results(fake)[0])
    expected = set(get_default_environment()) | set(granted)
    assert set(observed) == expected
    assert observed["PRAXIS_TASK_ID"] == "task-env-process-0001"
    assert "CANARY_SECRET" not in observed and "must-not-reach-mcp" not in observed.values()


async def test_tool_errors_are_counted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Tool calls and errors are recorded per tool (worker metrics; gate F3)."""
    from prometheus_client import REGISTRY

    labels = {"template": "local-default@2", "tool": "read_file"}
    before = REGISTRY.get_sample_value("praxis_tool_errors_total", labels) or 0
    calls_before = REGISTRY.get_sample_value("praxis_tool_calls_total", labels) or 0
    await run(
        script(
            {"tool": "read_file", "args": {"path": "missing.txt"}},
            {"tool": "finish_task", "args": {"status": "done", "summary": "ok"}},
        ),
        tmp_path,
        monkeypatch,
    )
    assert REGISTRY.get_sample_value("praxis_tool_errors_total", labels) == before + 1
    assert REGISTRY.get_sample_value("praxis_tool_calls_total", labels) == calls_before + 1


async def test_tool_and_token_events(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Phase 2 events plan D3, R6: the runner reports one token event per model
    response and a tool_call and tool_result per call, with no model or tool text,
    in the same order DSH does."""
    sink = MemorySink()
    with FakeModel(
        script(
            {"tool": "lookup_price", "args": {"sku": "SKU-1"}},
            {"tool": "write_file", "args": {"path": "summary.md", "content": "Total: 37.50\n"}},
            {"tool": "finish_task", "args": {"status": "done", "summary": "Wrote it."}},
        )
    ) as fake:
        await make_runner().run(
            config_for(fake, monkeypatch),
            tmp_path,
            make_store("events").session,
            "Write the order summary.",
            no_op,
            Usage(),
            AttemptEvents(sink, "wf", "task", 1, 1),
        )
    events = sink.events
    assert [e.type for e in events] == ["token", "tool_call", "tool_result"] * 3
    assert [e.payload["tool"] for e in events if e.type == "tool_call"] == [
        "lookup_price",
        "write_file",
        "finish_task",
    ]
    assert [e.payload["call"] for e in events if e.type == "tool_result"] == [1, 2, 3]
    assert {e.payload["status"] for e in events if e.type == "tool_result"} == {"ok"}
    counts = {"input_tokens", "output_tokens"}
    # DSH also names the gateway request (docs/roadmap/schemas.md); nothing else.
    tokens = [set(e.payload) for e in events if e.type == "token"]
    assert all(counts <= keys <= counts | {"request_id"} for keys in tokens)
    dumped = json.dumps([e.payload for e in events])
    assert "37.50" not in dumped and "summary" not in dumped.lower().replace("summary.md", "")


async def test_a_refused_finish_lets_the_model_wait(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Phase 2 messaging R19, D8: with an open question, finish_task("done") is
    refused and the run goes on; the model then finishes waiting."""
    with FakeModel(
        script(
            {"tool": "finish_task", "args": {"status": "done", "summary": "early"}},
            {"tool": "finish_task", "args": {"status": "waiting", "summary": "asked B"}},
        )
    ) as fake:
        config = replace(
            config_for(fake, monkeypatch), finish_check=lambda: ["open question q1 to B"]
        )
        result = await make_runner().run(
            config, tmp_path, make_store("refused-finish").session, "go", no_op, Usage(),
            attempt_events(),
        )  # fmt: skip
    assert result.status == "waiting" and result.summary == "asked B"
    assert len(fake.state.requests) == 2  # the refusal went back to the model
    refusal = tool_results(fake)[0]
    assert "refused" in refusal and "open question q1 to B" in refusal


def test_a_status_result_becomes_a_status_event() -> None:
    """Phase 2 messaging D15: only the validated stage and progress are published."""
    from harness_activity.events import AttemptEvents, MemorySink, emit_agent_status

    sink = MemorySink()
    events = AttemptEvents(sink, "wf", "task", 1, 1)
    emit_agent_status(events, '{"stage": "working", "progress": 40, "note": "secret"}')
    emit_agent_status(events, "not json")
    assert [(e.type, e.payload) for e in sink.events] == [
        ("status", {"stage": "working", "progress": 40, "source": "agent"})
    ]


async def test_an_mcp_status_result_is_published_on_openai_agents() -> None:
    """Review round 1: the SDK hands on_tool_end an MCP result as a text item (or a
    list of them), not a string; post_status must still become a status event, and
    an MCP error must still count as failed."""
    from types import SimpleNamespace

    from opentelemetry import trace

    from harness_activity.events import AttemptEvents, MemorySink
    from harness_activity.runner import _Hooks
    from harness_activity.tools import TurnState

    sink = MemorySink()

    async def before(usage: Usage) -> None:
        return None

    hooks = _Hooks(
        Usage(), set(), TurnState(), before, trace.get_tracer("t"), "t",
        AttemptEvents(sink, "wf", "task", 1, 1),
    )  # fmt: skip
    status = SimpleNamespace(name="post_status")
    text = '{"stage": "working", "progress": 40}'
    await hooks.on_tool_end(None, None, status, {"type": "text", "text": text})  # type: ignore[arg-type]
    await hooks.on_tool_end(None, None, status, [{"type": "text", "text": text}])  # type: ignore[arg-type]
    failing = SimpleNamespace(name="send_to_agent")
    await hooks.on_tool_end(None, None, failing, {"type": "text", "text": "Error: refused"})  # type: ignore[arg-type]
    published = [(e.type, e.payload) for e in sink.events]
    assert published.count(("status", {"stage": "working", "progress": 40, "source": "agent"})) == 2
    assert ("tool_result", {"tool": "send_to_agent", "call": None, "status": "failed"}) in published
