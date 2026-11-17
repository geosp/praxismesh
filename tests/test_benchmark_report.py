"""The benchmark report records what the spec asks for: per task, pass/fail, harness
and inner turns, tokens and wall time (spec quality/agent-benchmarks; gate F6)."""

from __future__ import annotations

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
        "Seconds",
    ]
    assert "| t01-order-total | pass | ok | 2 | 9 | 1 | 18 | 19717 | 900 | 48.4 |" in text
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
