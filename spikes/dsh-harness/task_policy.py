"""Pure decisions for the isolated DSH task Activity, unit-tested without Docker.

Failure classification, heartbeat progress, ownership order and run-manifest
validation live here so each rule is checked directly rather than only through
live probes.
"""

from __future__ import annotations

import re
from datetime import timedelta

import yaml
from run_probe import ROOT

TEMPLATE = yaml.safe_load((ROOT / "registry/templates/local-default.yaml").read_text())
PROFILE = yaml.safe_load((ROOT / "registry/profiles/default.yaml").read_text())
SKILL_BUNDLE = ROOT / "registry/skills" / TEMPLATE["skills_bundle"]
INNER_STEPS = int(TEMPLATE["inner_max_turns"])
CLEANUP_GRACE_SECONDS = 5
OBSERVATION_SECONDS = 10
BAD_INPUT_FAULTS = {"fixture rejected input", "provider rejected input"}
STEP_DENIALS = {"model-step limit", "token budget"}
ATTEMPT_ORDER_STRIDE = 1000


def iso_seconds(value: str) -> float:
    match = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", value)
    if match is None or not any(match.groups()):
        raise ValueError("unsupported ISO duration " + value)
    hours, minutes, seconds = (int(part or 0) for part in match.groups())
    return timedelta(hours=hours, minutes=minutes, seconds=seconds).total_seconds()


TURN_TIMEOUT_SECONDS = iso_seconds(TEMPLATE["turn_timeout"])


def attempt_order(turn: int, attempt: int) -> int:
    """Ownership order across one task's turns and Temporal attempts."""
    if not 1 <= attempt < ATTEMPT_ORDER_STRIDE or turn < 1:
        raise ValueError("turn and attempt must be positive and bounded")
    return turn * ATTEMPT_ORDER_STRIDE + attempt


def step_ceiling(case: str) -> int:
    return 2 if case == "inner-limit" else INNER_STEPS


def classify(
    *,
    blocked: bool = False,
    started: bool,
    cleanup_ok: bool,
    cooperative_stop: bool | None,
    settled: dict | None,
    fault: str | None,
    error_type: str | None,
    stop_reason: str | None,
    returncode: int | None,
    candidate: dict | None,
    finish: dict | None,
    denials: list[str],
) -> tuple[str, bool] | None:
    """(category, retryable) for a native attempt, or None when it succeeded.

    Order matters: cleanup and forced stop first (a forced stop fails R5 even if
    cleanup later succeeds), then unknown usage (never retried as if it were
    zero), then deterministic limits, before ordinary exit-code handling.
    """
    if started and not cleanup_ok:
        return "DshCleanupFailure", False
    if blocked:
        return "DshBlocked", False
    if cooperative_stop is False:
        return "DshForcedStop", False
    if settled is not None and settled.get("unknown_usage"):
        return "DshUsageUnknown", False
    if fault == "checkpoint limit" or error_type == "CheckpointLimit":
        return "DshCheckpointLimit", False
    if error_type == "Superseded":
        return "Superseded", True
    if stop_reason == "cancelled":
        return "DshCancelled", False
    if stop_reason is not None:
        return "DshTurnDeadline", True
    if not started or error_type is not None:
        # Staging, gateway or executor failures before or around launch.
        return "DshRuntimeFailure", True
    if returncode != 0 or candidate is None:
        return "DshRuntimeFailure", True
    if fault in BAD_INPUT_FAULTS:
        return "HarnessInputError", False
    if fault == "checkpoint barrier failed":
        return "DshCheckpointFailure", True
    if fault:
        return "DshProviderFailure", True
    if candidate.get("error_type"):
        return "DshProtocolFailure", True
    if (
        not finish
        and candidate.get("finish_reason") == "error"
        and not STEP_DENIALS.intersection(denials)
    ):
        return "DshModelFailure", True
    return None


def progress(attempt: int, prior: dict, settled: dict | None, admitted_tools: int = 0) -> dict:
    """Heartbeat details: cumulative over the turn, settled tokens never hidden."""
    settled = settled or {}
    return {
        "attempts": attempt,
        "tokens_in": prior.get("tokens_in", 0) + settled.get("input_tokens", 0),
        "tokens_out": prior.get("tokens_out", 0) + settled.get("output_tokens", 0),
        "tool_calls": prior.get("tool_calls", 0) + admitted_tools,
        "inner_turns": prior.get("inner_turns", 0) + settled.get("logical_steps", 0),
        "unknown_usage": prior.get("unknown_usage", 0) + settled.get("unknown_usage", 0),
    }


def prior_progress(details: list, rows: list[dict]) -> dict:
    """Turn usage so far: the larger of finished attempt rows and the heartbeat,
    which also covers an attempt lost before it recorded its row."""
    beat = details[0] if details else {}
    keys = ("tokens_in", "tokens_out", "tool_calls")
    from_rows = {key: sum(row.get(key) or 0 for row in rows) for key in keys}
    merged = {key: max(from_rows[key], int(beat.get(key, 0))) for key in keys}
    merged["inner_turns"] = int(beat.get("inner_turns", 0))
    merged["unknown_usage"] = int(beat.get("unknown_usage", 0))
    return merged


def task_inventory(benchmark: bool) -> dict:
    disabled = {"admission": "disabled", "bounds": "not admitted", "accounting": "not admitted"}
    inventory = {
        name: dict(disabled)
        for name in (
            "title_generation",
            "jobs",
            "compaction",
            "image_offload",
            "delegation",
            "mcp_resources",
            "dsh_skill_plugins",
            "dsh_native_file_and_shell_tools",
        )
    }
    inventory["internal_timers"] = {
        "admission": "internal only",
        "bounds": "turn deadline, cooperative SIGTERM within grace, observation window",
        "accounting": "no model/tool producer; gateway request ledger",
    }
    inventory["task_mcp_tools"] = {
        "admission": "trusted host executor catalog only",
        "bounds": "turn deadline; MCP call timeout 90s",
        "accounting": "every tool body entry recorded by the trusted executor",
    }
    if benchmark:
        inventory["template_skill_bundle"] = {
            "admission": "mounted read-only at workspace/.skills as in production",
            "bounds": "read through executor read_file",
            "accounting": "executor read_file body entries",
        }
    return inventory


STALE_PHASE01 = {
    "model_request_ceiling": "Phase 01 request cap; the task ledger owns model_step_ceiling",
    "probe_output_tokens_per_request": "Phase 01 quote-probe field",
    "inherited_inner_turns": "replaced by model_step_ceiling",
}


def validate_manifest(manifest: dict) -> list[str]:
    """Problems that must block a task-Activity run before the candidate starts."""
    problems = []
    required = (
        "case",
        "run_id",
        "task_id",
        "image",
        "source_commit",
        "outer_turn",
        "activity_attempt",
        "attempt_order",
        "wall_seconds",
        "model_step_ceiling",
        "task_token_ceiling",
        "cleanup_grace_seconds",
        "observation_seconds",
        "container_limits",
        "auxiliary_inventory",
        "granted_tools",
        "cli_tools",
    )
    problems += [f"missing {key}" for key in required if key not in manifest]
    m = manifest.get

    def check(keys: tuple, ok, message: str) -> None:
        if all(key in manifest for key in keys) and not ok():
            problems.append(message)

    check(
        ("source_commit",),
        lambda: re.fullmatch(r"[0-9a-f]{40}", str(m("source_commit"))),
        "source_commit is not a full SHA",
    )
    check(
        ("image",),
        lambda: re.fullmatch(r"sha256:[0-9a-f]{64}", str(m("image"))),
        "image is not a content ID",
    )
    for key in ("outer_turn", "activity_attempt", "task_token_ceiling", "model_step_ceiling"):
        check(
            (key,),
            lambda key=key: type(m(key)) is int and m(key) > 0,
            f"{key} must be a positive integer",
        )
    check(
        ("wall_seconds",),
        lambda: 0 < m("wall_seconds") <= TURN_TIMEOUT_SECONDS,
        "wall_seconds outside the template turn timeout",
    )
    check(
        ("model_step_ceiling",),
        lambda: m("model_step_ceiling") <= INNER_STEPS,
        "model_step_ceiling widens the template inner_max_turns",
    )
    task_cap = min(int(PROFILE["max_tokens"]), int(TEMPLATE["max_tokens_cap"]))
    check(
        ("task_token_ceiling",),
        lambda: m("task_token_ceiling") <= task_cap,
        "task_token_ceiling widens the profile/template cap",
    )
    check(
        ("cleanup_grace_seconds",),
        lambda: m("cleanup_grace_seconds") == CLEANUP_GRACE_SECONDS,
        "cleanup grace differs from the stop policy",
    )
    check(
        ("observation_seconds",),
        lambda: m("observation_seconds") == OBSERVATION_SECONDS,
        "observation window differs from the stop policy",
    )
    check(
        ("attempt_order", "outer_turn", "activity_attempt"),
        lambda: m("attempt_order") == attempt_order(m("outer_turn"), m("activity_attempt")),
        "attempt_order does not match turn/attempt",
    )
    check(
        ("cli_tools",),
        lambda: m("cli_tools") == TEMPLATE["cli_tools"],
        "cli_tools differ from the template grant",
    )
    check(
        ("auxiliary_inventory", "case"),
        lambda: m("auxiliary_inventory") == task_inventory(m("case") == "benchmark"),
        "auxiliary_inventory is not the Phase 02 task inventory",
    )
    if manifest.get("phase02_stop_oracle_pending") is not False:
        problems.append("stop oracle marked pending")
    for key, reason in STALE_PHASE01.items():
        if key in manifest:
            problems.append(f"stale field {key}: {reason}")
    return problems
    if not re.fullmatch(r"[0-9a-f]{40}", str(manifest["source_commit"])):
        problems.append("source_commit is not a full SHA")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", str(manifest["image"])):
        problems.append("image is not a content ID")
    for key in ("outer_turn", "activity_attempt", "task_token_ceiling", "model_step_ceiling"):
        if type(manifest[key]) is not int or manifest[key] <= 0:
            problems.append(f"{key} must be a positive integer")
    if not 0 < manifest["wall_seconds"] <= TURN_TIMEOUT_SECONDS:
        problems.append("wall_seconds outside the template turn timeout")
    if manifest["model_step_ceiling"] > INNER_STEPS:
        problems.append("model_step_ceiling widens the template inner_max_turns")
    task_cap = min(int(PROFILE["max_tokens"]), int(TEMPLATE["max_tokens_cap"]))
    if manifest["task_token_ceiling"] > task_cap:
        problems.append("task_token_ceiling widens the profile/template cap")
    if manifest["cleanup_grace_seconds"] != CLEANUP_GRACE_SECONDS:
        problems.append("cleanup grace differs from the stop policy")
    if manifest["observation_seconds"] != OBSERVATION_SECONDS:
        problems.append("observation window differs from the stop policy")
    if manifest["attempt_order"] != attempt_order(
        manifest["outer_turn"], manifest["activity_attempt"]
    ):
        problems.append("attempt_order does not match turn/attempt")
    if manifest["cli_tools"] != TEMPLATE["cli_tools"]:
        problems.append("cli_tools differ from the template grant")
    if manifest["auxiliary_inventory"] != task_inventory(manifest["case"] == "benchmark"):
        problems.append("auxiliary_inventory is not the Phase 02 task inventory")
    if manifest.get("phase02_stop_oracle_pending") is not False:
        problems.append("stop oracle marked pending")
    for key, reason in STALE_PHASE01.items():
        if key in manifest:
            problems.append(f"stale field {key}: {reason}")
    return problems
