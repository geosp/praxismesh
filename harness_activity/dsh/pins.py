"""Worker-side check of the DSH launcher's runtime report (DSH migration plan R17)."""

from __future__ import annotations

from typing import Any

from common.errors import CapabilityError


def verify_launcher_report(report: dict[str, Any], expected_digest: str) -> None:
    """Refuse to serve a DSH queue unless the launcher's pinned requirements digest
    matches the registry lock and every installed runtime file matched its wheel."""
    if report.get("integrity") != "ok":
        raise CapabilityError(
            "DSH runtime integrity check failed: "
            f"{report.get('integrity')} {report.get('mismatches') or report.get('detail') or ''}"
        )
    if report.get("requirements_digest") != expected_digest:
        raise CapabilityError(
            f"DSH runtime {report.get('requirements_digest')} does not match the registry "
            f"lock {expected_digest}"
        )
