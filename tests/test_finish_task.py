"""`finish_task` keeps at most 20 questions of at most 500 characters each, as it
keeps at most 2,000 characters of the summary (Phase 3A persistence plan phase 01
task 3.2; D9)."""

from __future__ import annotations

from harness_activity.tools import (
    QUESTION_MAX_CHARS,
    QUESTIONS_MAX,
    TurnState,
    finish_task_body,
)


def test_questions_are_truncated() -> None:
    state = TurnState()
    questions = [f"{i:02d}" + "q" * 598 for i in range(21)]
    assert finish_task_body(state, "needs_input", "s" * 2500, questions) == "recorded"
    assert state.finish is not None
    kept = state.finish.questions
    assert (QUESTIONS_MAX, QUESTION_MAX_CHARS) == (20, 500)
    assert len(kept) == 20 and [q[:2] for q in kept] == [f"{i:02d}" for i in range(20)]
    assert all(len(q) == 500 for q in kept)
    assert kept == [q[:500] for q in questions[:20]]
    assert len(state.finish.summary) == 2000


def test_short_questions_are_unchanged() -> None:
    state = TurnState()
    finish_task_body(state, "needs_input", "s", ["Which SKU?"])
    assert state.finish is not None and state.finish.questions == ["Which SKU?"]
    finish_task_body(state, "done", "s")
    assert state.finish.questions == []
