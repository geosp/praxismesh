"""Round-1 implementation review regressions (F1-F17), without Docker or Temporal."""

import json

import pytest
from recovery_store import Authority, CheckpointLimit, FlushMissing, Superseded, capture_pair
from run_probe import ROOT
from task_boundary import latest_tool_call_id
from task_policy import (
    INNER_STEPS,
    attempt_order,
    classify,
    prior_progress,
    progress,
    step_ceiling,
    task_inventory,
    validate_manifest,
)
from usage_ledger import UsageLedger

BASE = dict(
    started=True,
    cleanup_ok=True,
    cooperative_stop=None,
    settled={"unknown_usage": 0},
    fault=None,
    error_type=None,
    stop_reason=None,
    returncode=0,
    candidate={"finish_reason": "completed"},
    finish={"status": "done"},
    denials=[],
)


def test_f1_heartbeat_keeps_settled_tokens_while_a_request_is_in_flight():
    ledger = UsageLedger("run", "task", 1, 1000)
    ledger.settle(ledger.ingress("main", 1), {"prompt_tokens": 7, "completion_tokens": 3})
    ledger.ingress("main", 2)  # dispatched, response still held
    assert ledger.totals()["input_tokens"] is None  # totals hide it ...
    beat = progress(1, {"tokens_in": 0, "tokens_out": 0}, ledger.settled())
    assert (beat["tokens_in"], beat["tokens_out"], beat["unknown_usage"]) == (7, 3, 1)
    assert beat["inner_turns"] == 2  # F14


def test_f2_unknown_usage_is_classified_before_exit_code():
    crash = dict(BASE, returncode=137, candidate=None, settled={"unknown_usage": 1})
    assert classify(**crash) == ("DshUsageUnknown", False)


def test_f3_retry_after_lost_attempts_carries_heartbeat_usage():
    # Five lost attempts of 7+3 tokens each, none of which wrote its row.
    details = [{}]
    for attempt in range(1, 6):
        details = [
            progress(attempt, prior_progress(details, []), {"input_tokens": 7, "output_tokens": 3})
        ]
    exhausted = prior_progress(details, [])
    assert (exhausted["tokens_in"], exhausted["tokens_out"]) == (35, 15)


def test_f4_pre_launch_failures_stay_retryable_runtime_failures():
    staging = dict(BASE, started=False, cleanup_ok=False, error_type="OSError", returncode=None)
    assert classify(**staging) == ("DshRuntimeFailure", True)
    assert classify(**dict(staging, error_type="RuntimeError"), blocked=True) == (
        "DshBlocked",
        False,
    )


def test_f5_stale_attempt_cannot_reclaim_after_a_newer_one(tmp_path):
    authority = Authority(tmp_path / "authority.sqlite")
    assert authority.claim(attempt_order(1, 2)) == 1002
    with pytest.raises(Superseded):
        authority.claim(attempt_order(1, 1))
    assert authority.owns(1002) and not authority.owns(1001)
    assert authority.claim(attempt_order(2, 1)) == 2001  # next turn still advances


def test_f6_superseded_owner_check_is_available_before_rows_and_blobs(tmp_path):
    authority = Authority(tmp_path / "authority.sqlite")
    old = authority.claim(attempt_order(1, 1))
    authority.claim(attempt_order(1, 2))
    assert not authority.owns(old)
    with pytest.raises(Superseded):
        authority.acknowledge(old, b"{}", {"finish": None})


def make_state(tmp_path, session=b"{}"):
    (tmp_path / "home/sessions").mkdir(parents=True)
    (tmp_path / "home/sessions/s.jsonl").write_bytes(session)
    (tmp_path / "workspace").mkdir()
    return tmp_path


def test_f7_acknowledgement_requires_the_latest_tool_result_in_the_session(tmp_path):
    state = make_state(tmp_path, b'{"tool_call_id": "call-1"}\n')
    request = {"messages": [{"role": "tool", "tool_call_id": "call-1"}]}
    capture_pair(state, None, session_marker=latest_tool_call_id(request))
    newer = {"messages": [*request["messages"], {"role": "tool", "tool_call_id": "call-2"}]}
    with pytest.raises(FlushMissing):
        capture_pair(state, None, session_marker=latest_tool_call_id(newer))


def test_f8_benchmark_inventory_has_no_unobserved_skill_tool():
    inventory = task_inventory(benchmark=True)
    assert inventory["dsh_skill_plugins"]["admission"] == "disabled"
    assert "executor read_file" in inventory["template_skill_bundle"]["accounting"]


def frozen_task_manifest():
    evidence = json.loads((ROOT / "docs/spikes/dsh-phase02-evidence.json").read_text())
    return next(r["manifest"] for r in evidence["runs"] if r["manifest"]["case"] == "done")


def test_f9_validator_rejects_the_round1_frozen_manifests():
    problems = validate_manifest(frozen_task_manifest())
    assert any("auxiliary_inventory" in p for p in problems)
    assert any("model_request_ceiling" in p for p in problems)


def test_f9_validator_accepts_a_consistent_task_manifest():
    manifest = frozen_task_manifest()
    for key in (
        "model_request_ceiling",
        "probe_output_tokens_per_request",
        "inherited_inner_turns",
    ):
        manifest.pop(key, None)
    manifest.update(
        attempt_order=attempt_order(manifest["outer_turn"], manifest["activity_attempt"]),
        auxiliary_inventory=task_inventory(False),
        granted_tools=["finish_task"],
        cli_tools=["python3", "wc", "git", "sh"],
    )
    assert validate_manifest(manifest) == []
    assert validate_manifest(dict(manifest, model_step_ceiling=INNER_STEPS + 1))


def test_f10_checkpoint_limits_are_deterministic_and_non_retryable(tmp_path):
    state = make_state(tmp_path)
    (state / "workspace/link").symlink_to("/etc/hostname")
    with pytest.raises(CheckpointLimit):
        capture_pair(state, None)
    # Production workspace semantics skip links and the read-only skill mount.
    (state / "workspace/.skills").mkdir()
    (state / "workspace/.skills/SKILL.md").write_text("skill")
    files = json.loads(capture_pair(state, None, workspace_policy="production"))
    assert not any(k.startswith(("workspace/link", "workspace/.skills")) for k in files)
    assert classify(**dict(BASE, fault="checkpoint limit")) == ("DshCheckpointLimit", False)


def test_f11_forced_stop_fails_even_when_cleanup_succeeds():
    forced = dict(BASE, cooperative_stop=False, stop_reason="turn deadline exceeded")
    assert classify(**forced) == ("DshForcedStop", False)
    assert classify(**dict(forced, cooperative_stop=True)) == ("DshTurnDeadline", True)
    assert classify(**dict(forced, cooperative_stop=True, stop_reason="cancelled")) == (
        "DshCancelled",
        False,
    )


def test_f13_ceilings_come_from_the_template():
    assert step_ceiling("done") == INNER_STEPS
    assert step_ceiling("inner-limit") == 2


def test_step_and_budget_denials_are_continuation_not_model_failure():
    stopped = dict(BASE, finish=None, candidate={"finish_reason": "error"})
    assert classify(**stopped) == ("DshModelFailure", True)
    assert classify(**dict(stopped, denials=["model-step limit"])) is None
