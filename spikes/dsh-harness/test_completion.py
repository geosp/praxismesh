"""Run with the root uv project; the isolated candidate project has no Agents SDK."""

import pytest

pytest.importorskip("agents")

from pydantic import ValidationError
from recovery_boundary import Refused
from task_completion import Completion, turn_outcome


@pytest.mark.parametrize(
    "arguments",
    [
        {"status": "succeeded", "summary": "invalid status", "questions": None},
        {"status": "done", "summary": 123, "questions": None},
        {
            "status": "done",
            "summary": "invalid reference",
            "questions": None,
            "artifacts": [{"path": "../escape", "ref": {"checksum": "bad"}}],
        },
    ],
)
def test_invalid_completion_cannot_establish_success(tmp_path, arguments):
    completion = Completion(tmp_path)
    with pytest.raises(Refused):
        completion.dispatch("finish_task", arguments)
    assert completion.report() is None
    assert not completion.finished.is_set()
    completion.dispatch(
        "finish_task", {"status": "done", "summary": "corrected", "questions": None}
    )
    assert completion.report()["status"] == "done"


def test_needs_input_preserves_questions_and_cannot_be_overwritten(tmp_path):
    completion = Completion(tmp_path)
    completion.dispatch(
        "finish_task",
        {"status": "needs_input", "summary": "choose input", "questions": ["Which fixture value?"]},
    )
    assert completion.report()["questions"] == ["Which fixture value?"]
    with pytest.raises(Refused):
        completion.dispatch(
            "finish_task", {"status": "done", "summary": "overwrite", "questions": None}
        )


def test_no_finish_means_continuation_and_unknown_usage_blocks_publication():
    totals = dict(input_tokens=7, output_tokens=3, logical_steps=1, unknown_usage=0)
    result = turn_outcome(None, totals, checkpoint="ack", tool_calls=0, outputs=[])
    assert result.status == "continue" and not result.outputs
    with pytest.raises(RuntimeError, match="unresolved physical usage"):
        turn_outcome(
            None, dict(totals, unknown_usage=1), checkpoint="ack", tool_calls=0, outputs=[]
        )


def test_malformed_artifact_reference_is_rejected_by_actual_schema():
    totals = dict(input_tokens=7, output_tokens=3, logical_steps=1, unknown_usage=0)
    with pytest.raises(ValidationError):
        turn_outcome(
            dict(status="done", summary="fixture", questions=[]),
            totals,
            checkpoint="ack",
            tool_calls=1,
            outputs=[dict(path="../escape", ref={})],
        )
