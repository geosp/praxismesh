"""Failure classification for a DSH attempt (DSH migration plan D2, R8, R9, R13).

Ported from the spike's `task_policy.classify`, where each rule has a recorded
case (docs/spikes/dsh-phase02-r2-evidence.json).
"""

from __future__ import annotations

from typing import Any

BAD_INPUT_FAULTS = frozenset({"provider rejected input"})
STEP_DENIALS = frozenset({"model-step limit", "token budget"})
CLEANUP_GRACE_SECONDS = 5.0
OBSERVATION_SECONDS = 10.0


def classify(
    *,
    started: bool,
    cleanup_ok: bool,
    cooperative_stop: bool | None,
    unknown_usage: int,
    fault: str | None,
    error_type: str | None,
    stop_reason: str | None,
    returncode: int | None,
    candidate: dict[str, Any] | None,
    finished: bool,
    denials: list[str],
    blocked: bool = False,
) -> tuple[str, bool] | None:
    """(category, retryable) for an attempt, or None when it ran to a valid end.

    Order matters. Failed cleanup and a forced stop come first: a forced stop is a
    failure even when the kill succeeds (R9). Unknown usage follows and is
    retryable, because the next attempt charges it conservatively (D9). Then
    deterministic failures, before ordinary exit handling.
    """
    if started and not cleanup_ok:
        return "DshCleanupFailure", False
    if blocked:
        return "DshBlocked", False
    if cooperative_stop is False:
        return "DshForcedStop", False
    if fault == "checkpoint limit" or error_type == "CheckpointLimit":
        return "DshCheckpointLimit", False
    if error_type == "Superseded":
        return "Superseded", True
    if stop_reason == "cancelled":
        return "DshCancelled", False
    if unknown_usage:
        return "DshUsageUnknown", True
    if stop_reason is not None:
        return "DshTurnDeadline", True
    if not started or error_type is not None:
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
        not finished
        and candidate.get("finish_reason") == "error"
        and not STEP_DENIALS.intersection(denials)
    ):
        return "DshModelFailure", True
    return None
