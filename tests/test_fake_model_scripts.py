"""The fake model's multi-agent scripts (Phase 2 messaging D16, task 1.1): a
`[script:NAME]` marker picks the script, `${result.N.field}` reuses a field of an
earlier tool result, and `${input:REGEX}` a value from the task's input."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tests.support.fake_model import FakeModelState, load_scripts

SCRIPTS: dict[str, Any] = {
    "default": [{"text": "default"}],
    "asker": [
        {"tool": "ask_agent", "args": {"task_id": "${input:ask task (\\S+)}", "text": "price?"}},
        {
            "tool": "finish_task",
            "args": {"status": "waiting", "summary": "${result.0.correlation_id}"},
        },
        {"text": "done"},
    ],
}


def call(reply: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    function = reply["choices"][0]["message"]["tool_calls"][0]["function"]
    return function["name"], json.loads(function["arguments"])


def test_a_marker_picks_the_script_and_input_fills_an_argument() -> None:
    state = FakeModelState(SCRIPTS)
    reply = state.reply({"messages": [
        {"role": "system", "content": "[script:asker] You are A."},
        {"role": "user", "content": "Please ask task task-b-42 for the price."},
    ]})  # fmt: skip
    assert call(reply) == ("ask_agent", {"task_id": "task-b-42", "text": "price?"})


def test_a_request_without_a_marker_gets_the_default_script() -> None:
    reply = FakeModelState(SCRIPTS).reply({"messages": [{"role": "user", "content": "hi"}]})
    assert reply["choices"][0]["message"]["content"] == "default"


def test_a_result_reference_reads_an_earlier_tool_result() -> None:
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": "[script:asker]"},
        {"role": "user", "content": "ask task task-b"},
        {"role": "assistant", "content": None, "tool_calls": [{"id": "c0", "type": "function",
         "function": {"name": "ask_agent", "arguments": "{}"}}]},
        # an MCP result can arrive as a list of text parts
        {"role": "tool", "tool_call_id": "c0",
         "content": [{"type": "text", "text": json.dumps({"correlation_id": "q-7"})}]},
    ]  # fmt: skip
    assert call(FakeModelState(SCRIPTS).reply({"messages": messages})) == (
        "finish_task",
        {"status": "waiting", "summary": "q-7"},
    )


def test_the_newest_input_wins() -> None:
    script = {"default": [{"tool": "t", "args": {"q": "${input:Question (\\S+) from}"}}]}
    reply = FakeModelState(script).reply({"messages": [
        {"role": "user", "content": "Question old from A"},
        {"role": "user", "content": "Question new from A"},
    ]})  # fmt: skip
    assert call(reply) == ("t", {"q": "new"})


def test_a_single_script_list_still_works() -> None:
    reply = FakeModelState([{"text": "only"}]).reply({"messages": []})
    assert reply["choices"][0]["message"]["content"] == "only"


def test_a_scripts_file_may_name_other_script_files(tmp_path: Path) -> None:
    (tmp_path / "order.json").write_text(json.dumps([{"text": "order"}]))
    (tmp_path / "scripts.json").write_text(
        json.dumps({"default": "order.json", "b": [{"text": "b"}]})
    )
    scripts = load_scripts(tmp_path / "scripts.json")
    assert scripts == {"default": [{"text": "order"}], "b": [{"text": "b"}]}
