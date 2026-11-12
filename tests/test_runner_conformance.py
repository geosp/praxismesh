"""`HarnessRunner` conformance against the deterministic fake model, with the real
sample MCP server as a subprocess (spec execution/harness-turn; RFC Testing).

Runs in the unit suite: no stack needed (read-only MCP tools only)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
from agents import SQLiteSession

from common.observability import disable_sdk_tracing
from harness_activity.config import HarnessConfig, build_config
from harness_activity.runner import OpenAIAgentsRunner, Usage
from registry.loader import load_registry
from tests.support.fake_model import FakeModel


def script(*steps: dict[str, Any]) -> list[dict[str, Any]]:
    return list(steps)


@pytest.fixture(autouse=True)
def _no_sdk_tracing() -> None:
    disable_sdk_tracing()


def config_for(fake: FakeModel, monkeypatch: pytest.MonkeyPatch) -> HarnessConfig:
    monkeypatch.setenv("VLLM_BASE_URL", fake.base_url)
    registry = load_registry()
    _, loaded = registry.resolve("default")
    return build_config(registry, loaded, "task-conformance-0001")


async def no_op(usage: Usage) -> None:
    return None


async def run(
    steps: list[dict[str, Any]], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Any, FakeModel]:
    with FakeModel(steps) as fake:
        result = await OpenAIAgentsRunner().run(
            config_for(fake, monkeypatch),
            tmp_path,
            SQLiteSession("conformance"),
            "Write the order summary.",
            no_op,
            Usage(),
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
    }
    system = first["messages"][0]["content"]
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
        result = await OpenAIAgentsRunner().run(
            config, tmp_path, SQLiteSession("stop"), "go", stop_on_second_call, Usage()
        )
        assert result.status == "continue" and result.summary == "budget"
        assert len(fake.state.requests) == 1

        async def superseded(usage: Usage) -> None:
            raise Superseded("newer attempt")

        with pytest.raises(Superseded):
            await OpenAIAgentsRunner().run(
                config, tmp_path, SQLiteSession("sup"), "go", superseded, Usage()
            )
