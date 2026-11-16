"""Worker-side check of the DSH launcher's runtime report (DSH migration plan R17)."""

from __future__ import annotations

from typing import Any

from common.errors import CapabilityError
from harness_activity.runner import Unserviceable


class RuntimePinMismatch(Unserviceable):
    """The DSH container this worker is paired with no longer runs the pinned
    runtime (it was recreated from another image). Retryable: the attempt is
    refused here, and a worker paired with the pinned runtime may take it (R17)."""


def verify_launcher_report(report: dict[str, Any], expected_digest: str) -> None:
    """Refuse to serve a DSH queue unless the launcher's runtime digest (pinned
    requirements and control files) matches the registry lock and every installed
    runtime file matched its wheel."""
    if report.get("integrity") != "ok":
        raise CapabilityError(
            "DSH runtime integrity check failed: "
            f"{report.get('integrity')} {report.get('mismatches') or report.get('detail') or ''}"
        )
    if report.get("runtime_digest") != expected_digest:
        raise CapabilityError(
            f"DSH runtime {report.get('runtime_digest')} does not match the registry "
            f"lock {expected_digest}"
        )
