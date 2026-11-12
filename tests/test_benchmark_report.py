"""The benchmark report records what the spec asks for: per task, pass/fail, harness
and inner turns, tokens and wall time (spec quality/agent-benchmarks; gate F6)."""

from __future__ import annotations

from tests.benchmarks.run import markdown, verdict_for

ENV = {
    "date": "2026-11-12",
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
    for key in ("template", "model", "harness", "prompt_hash"):
        assert ENV[key] in text


def test_regression_limit(tmp_path: object, monkeypatch: object) -> None:
    import json

    import tests.benchmarks.run as run

    baseline = run.OUT / "baseline.json"
    passed = json.loads(baseline.read_text())["passed"]
    assert "Within the regression limit" in verdict_for(passed - 1, make_baseline=False)
    assert "Regression limit exceeded" in verdict_for(passed - 2, make_baseline=False)
