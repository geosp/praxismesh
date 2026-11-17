"""The benchmark report records what the spec asks for: per task, pass/fail, harness
and inner turns, tokens and wall time (spec quality/agent-benchmarks; gate F6)."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

import pytest

from tests.benchmarks.run import markdown, verdict_for

ENV = {
    "date": "2026-11-12",
    "profile": "default",
    "template": "local-default@1",
    "template_hash": "sha256:x",
    "model": "spark",
    "harness": "openai-agents 0.24.0",
    "prompt_hash": "sha256:y",
}
ROW = {
    "task": "t01-order-total",
    "task_id": "task-x",
    "passed": True,
    "check": "ok",
    "status": "succeeded",
    "failure_reason": None,
    "turns": 2,
    "inner_turns": 9,
    "attempts": 1,
    "tool_calls": 18,
    "tokens_in": 19717,
    "tokens_out": 900,
    "seconds": 48.4,
}


def test_report_has_every_required_column() -> None:
    text = markdown(ENV, [ROW], "verdict")
    header = next(line for line in text.splitlines() if line.startswith("| Task |"))
    assert [c.strip() for c in header.strip("|").split("|")] == [
        "Task",
        "Result",
        "Check",
        "Turns",
        "Inner turns",
        "Attempts",
        "Tool calls",
        "Tokens in",
        "Tokens out",
        "Usage known",
        "Seconds",
    ]
    assert "| t01-order-total | pass | ok | 2 | 9 | 1 | 18 | 19717 | 900 | None | 48.4 |" in text
    assert text.startswith("# Agent benchmark: default (local-default@1), 2026-11-12")
    for key in ("profile", "template", "model", "harness", "prompt_hash"):
        assert ENV[key] in text


def test_regression_limit(tmp_path: object, monkeypatch: object) -> None:
    import json

    import tests.benchmarks.run as run

    baseline = run.OUT / "baseline.json"
    passed = json.loads(baseline.read_text())["passed"]
    assert "Within the regression limit" in verdict_for(passed - 1, make_baseline=False)
    assert "Regression limit exceeded" in verdict_for(passed - 2, make_baseline=False)


def test_profile_picks_template_and_harness_label() -> None:
    """--profile takes the template from the profile and labels its harness
    (DSH migration plan phase 03 task 1.1)."""
    from tests.benchmarks.run import harness_label, profile_template

    openai = profile_template("openai")
    assert openai.template.harness == "openai_agents"
    assert harness_label(openai).startswith("openai-agents ")
    dsh = profile_template("dsh")
    assert dsh.template.name == "local-dsh"
    assert harness_label(dsh).startswith("deepseek-harness-sdk 0.")


def test_run_outside_docs_is_not_judged() -> None:
    assert "Not judged" in verdict_for(0, make_baseline=False, judged=False)


# Phase 03 impl review round 1 (F170-F172, F177, F187, F189).


async def main_exits(argv: list[str]) -> str:
    import tests.benchmarks.run as run

    with pytest.raises(SystemExit) as raised:
        await run.main(argv)
    assert raised.value.code == 2
    return str(raised.value)


async def test_unknown_task_id_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """F171: an unknown --only ID must not run zero tasks and exit 0."""
    await main_exits(["--only", "fizzbuzz", "--out", str(tmp_path)])
    assert "unknown task" in capsys.readouterr().err


async def test_subset_is_not_written_to_docs(capsys: pytest.CaptureFixture[str]) -> None:
    """F171: a subset run is never judged against, or written over, the full results."""
    await main_exits(["--only", "t01-order-total"])
    assert "--out" in capsys.readouterr().err


async def test_baseline_only_from_openai_agents(capsys: pytest.CaptureFixture[str]) -> None:
    """F172: the baseline rule's reference stays an openai_agents run."""
    await main_exits(["--profile", "dsh", "--baseline"])
    assert "openai_agents" in capsys.readouterr().err


class StuckHandle:
    def __init__(self) -> None:
        self.terminated: str | None = None

    async def result(self) -> Any:
        await asyncio.Event().wait()

    async def terminate(self, reason: str) -> None:
        self.terminated = reason


async def test_result_wait_stops_when_the_worker_stops_serving(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """F170: a worker that stops polling ends the run instead of every task
    waiting out schedule_to_close."""
    import tests.benchmarks.run as run
    import workers.main

    monkeypatch.setattr(workers.main, "UNSERVICEABLE", [])
    handle = StuckHandle()
    waiting = asyncio.ensure_future(run.await_result(handle, poll=0.01))
    await asyncio.sleep(0.05)
    assert not waiting.done()
    workers.main.UNSERVICEABLE.append("launcher reports a dirty attempt")
    with pytest.raises(run.WorkerStopped, match="dirty attempt"):
        await asyncio.wait_for(waiting, 2)
    assert handle.terminated is not None


def test_results_are_written_as_tasks_finish(tmp_path: Path) -> None:
    """F187: finished rows survive a later failure; F177: rows carry usage_known."""
    import tests.benchmarks.run as run

    stem = run.write_results(tmp_path, {**ENV}, [{**ROW, "usage_known": False}], "Incomplete.")
    data = json.loads(stem.with_suffix(".json").read_text())
    assert data["passed"] == 1 and data["rows"][0]["usage_known"] is False
    assert stem.name == "2026-11-12-default"
    assert "| Usage known |" in stem.with_suffix(".md").read_text()


def test_paired_dsh_restores_dsh_control(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """F189 and F174: the DSH branch sets DSH_CONTROL for the workers, then
    restores what was there, and stops its container."""
    import tests.benchmarks.run as run

    stopped: list[bool] = []

    class Container:
        control = tmp_path / ".control.sock"

        def stop(self) -> None:
            stopped.append(True)

    monkeypatch.setattr(run, "build_image", lambda: "image")
    monkeypatch.setattr(run, "start_container", lambda image: Container())
    monkeypatch.setenv("DSH_CONTROL", "/earlier")
    with run.paired_dsh(run.profile_template("dsh")):
        assert os.environ["DSH_CONTROL"] == str(Container.control)
    assert os.environ["DSH_CONTROL"] == "/earlier" and stopped == [True]
    with run.paired_dsh(run.profile_template("openai")):
        assert os.environ["DSH_CONTROL"] == "/earlier"
