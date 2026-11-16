"""DSH gateway ledger, failure classification and barrier (migration plan task 2.2).

Ported from the spike's test_usage_ledger.py and test_task_policy.py.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from harness_activity.dsh.barrier import (
    BarrierFailed,
    latest_tool_call_id,
    pack_session,
    run_barrier,
    session_contains,
)
from harness_activity.dsh.ledger import DSH_MAX_OUTPUT_TOKENS, UsageLedger, unknown_charge
from harness_activity.dsh.policy import classify

USAGE = {"prompt_tokens": 7, "completion_tokens": 3}


class MemoryStore:
    def __init__(self) -> None:
        self.rows: dict[str, tuple[int, int] | None] = {}

    async def dispatch(self, task_id: str, turn: int, attempt: int, rid: str, purpose: str) -> None:
        self.rows[rid] = None

    async def settle(
        self, task_id: str, turn: int, attempt: int, rid: str, incoming: int, outgoing: int
    ) -> None:
        self.rows[rid] = (incoming, outgoing)


def ledger(budget: int = 10, steps: int = 8) -> tuple[UsageLedger, MemoryStore]:
    store = MemoryStore()
    return UsageLedger(store, "task", 1, 1, budget, steps), store


async def test_exhaustion_denies_the_next_request_and_keeps_the_denial() -> None:
    led, store = ledger()
    await led.settle(await led.admit("main", 1), USAGE)
    denied = await led.admit("main", 2)
    assert (denied.dispatched, denied.denial) == (False, "token budget")
    assert led.denials() == ["token budget"] and list(store.rows) == ["req-0001"]


async def test_retry_is_two_dispatches_of_one_logical_step() -> None:
    led, _ = ledger()
    await led.settle(await led.admit("main", 1), None, known_zero=True)
    await led.settle(await led.admit("retry", 1), USAGE)
    assert led.settled() == {
        "input_tokens": 7, "output_tokens": 3, "unknown_usage": 0, "logical_steps": 1,
    }  # fmt: skip


async def test_row_is_written_before_dispatch_and_stays_open_when_unsettled() -> None:
    led, store = ledger(budget=1000)
    first = await led.admit("main", 1)
    assert store.rows == {"req-0001": None}  # durable before the request is sent
    await led.settle(first, None)  # no usage observed
    assert store.rows == {"req-0001": None}
    assert (await led.admit("main", 2)).denial == "unresolved usage"


async def test_in_flight_request_does_not_hide_settled_tokens() -> None:
    led, _ = ledger(budget=1000)
    await led.settle(await led.admit("main", 1), USAGE)
    await led.admit("main", 2)
    assert led.settled() == {
        "input_tokens": 7, "output_tokens": 3, "unknown_usage": 1, "logical_steps": 2,
    }  # fmt: skip


async def test_step_ceiling_is_recorded_as_a_denial() -> None:
    led, _ = ledger(budget=1000, steps=2)
    for step in (1, 2):
        await led.settle(await led.admit("main", step), USAGE)
    assert (await led.admit("main", 3)).denial == "model-step limit"


async def test_invalid_usage_is_rejected() -> None:
    led, _ = ledger()
    record = await led.admit("main", 1)
    with pytest.raises(ValueError):
        await led.settle(record, {"prompt_tokens": "7", "completion_tokens": 3})


def test_unknown_requests_are_charged_the_window_plus_the_output_cap() -> None:
    assert unknown_charge(2, 32768) == (65536, 2 * DSH_MAX_OUTPUT_TOKENS)
    assert unknown_charge(0, 32768) == (0, 0)


BASE: dict[str, Any] = dict(
    started=True, cleanup_ok=True, cooperative_stop=None, unknown_usage=0, fault=None,
    error_type=None, stop_reason=None, returncode=0, candidate={"finish_reason": "completed"},
    finished=True, denials=[],
)  # fmt: skip


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ({}, None),
        ({"cleanup_ok": False}, ("DshCleanupFailure", False)),
        ({"cooperative_stop": False, "stop_reason": "deadline"}, ("DshForcedStop", False)),
        ({"cooperative_stop": True, "stop_reason": "deadline"}, ("DshTurnDeadline", True)),
        ({"cooperative_stop": True, "stop_reason": "cancelled"}, ("DshCancelled", False)),
        # D9: a crash with unknown usage is retried; the next attempt charges it.
        ({"returncode": 137, "candidate": None, "unknown_usage": 1}, ("DshUsageUnknown", True)),
        ({"fault": "checkpoint limit"}, ("DshCheckpointLimit", False)),
        ({"fault": "checkpoint barrier failed"}, ("DshCheckpointFailure", True)),
        ({"fault": "provider rejected input"}, ("HarnessInputError", False)),
        ({"fault": "provider transport failure"}, ("DshProviderFailure", True)),
        ({"started": False, "cleanup_ok": False, "error_type": "OSError", "returncode": None},
         ("DshRuntimeFailure", True)),
        ({"started": False, "error_type": "RuntimeError", "blocked": True}, ("DshBlocked", False)),
        ({"finished": False, "candidate": {"finish_reason": "error"}}, ("DshModelFailure", True)),
        ({"finished": False, "candidate": {"finish_reason": "error"},
          "denials": ["model-step limit"]}, None),
    ],
)  # fmt: skip
def test_classification(change: dict[str, Any], expected: tuple[str, bool] | None) -> None:
    assert classify(**{**BASE, **change}) == expected


def session(tmp_path: Path, text: str) -> Path:
    directory = tmp_path / "sessions"
    directory.mkdir()
    (directory / "s.jsonl").write_text(text)
    return directory


def request_with(*ids: str) -> dict[str, Any]:
    return {"messages": [{"role": "tool", "tool_call_id": i} for i in ids]}


class Attempt:
    def __init__(self, freeze_ok: bool = True, thaw_ok: bool = True, commit_error: bool = False):
        self.freeze_ok, self.thaw_ok, self.commit_error = freeze_ok, thaw_ok, commit_error
        self.calls: list[str] = []

    async def freeze(self) -> bool:
        self.calls.append("freeze")
        return self.freeze_ok

    async def thaw(self) -> bool:
        self.calls.append("thaw")
        return self.thaw_ok

    async def commit(self) -> None:
        self.calls.append("commit")
        if self.commit_error:
            raise RuntimeError("fence rejected")


async def barrier(attempt: Attempt, directory: Path, request: dict[str, Any]) -> None:
    await run_barrier(
        request=request, session_dir=directory, freeze=attempt.freeze, thaw=attempt.thaw,
        capture_and_commit=attempt.commit,
    )  # fmt: skip


async def test_barrier_freezes_commits_and_thaws_in_order(tmp_path: Path) -> None:
    directory, attempt = session(tmp_path, '{"tool_call_id": "call-2"}'), Attempt()
    assert latest_tool_call_id(request_with("call-1", "call-2")) == "call-2"
    await barrier(attempt, directory, request_with("call-1", "call-2"))
    assert attempt.calls == ["freeze", "commit", "thaw"]


async def test_barrier_refuses_an_unflushed_session_without_freezing(tmp_path: Path) -> None:
    directory, attempt = session(tmp_path, '{"tool_call_id": "call-1"}'), Attempt()
    assert not session_contains(directory, "call-2")
    with pytest.raises(BarrierFailed, match="not in the session"):
        await barrier(attempt, directory, request_with("call-1", "call-2"))
    assert attempt.calls == []  # no checkpoint, nothing frozen


async def test_first_request_has_no_marker_to_check(tmp_path: Path) -> None:
    attempt = Attempt()
    await barrier(attempt, session(tmp_path, "{}"), {"messages": [{"role": "user"}]})
    assert attempt.calls == ["freeze", "commit", "thaw"]


@pytest.mark.parametrize(
    ("attempt", "calls", "error"),
    [
        (Attempt(freeze_ok=False), ["freeze", "thaw"], BarrierFailed),
        (Attempt(commit_error=True), ["freeze", "commit", "thaw"], RuntimeError),
        (Attempt(thaw_ok=False), ["freeze", "commit", "thaw"], BarrierFailed),
    ],
)
async def test_barrier_always_thaws_and_reports_failure(
    tmp_path: Path, attempt: Attempt, calls: list[str], error: type[Exception]
) -> None:
    with pytest.raises(error):
        await barrier(attempt, session(tmp_path, "{}"), {"messages": []})
    assert attempt.calls == calls


def test_session_archive_is_deterministic(tmp_path: Path) -> None:
    directory = session(tmp_path, "one")
    first, second = pack_session(directory), pack_session(directory)
    assert first == second and first[1].startswith("sha256:")
    (directory / "s.jsonl").write_text("two")
    assert pack_session(directory)[1] != first[1]
