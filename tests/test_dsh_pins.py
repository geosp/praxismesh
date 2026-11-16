"""DSH runtime pins: lock and image agree, and the worker refuses a mismatch (R17)."""

from __future__ import annotations

import pytest

from common.errors import CapabilityError
from harness_activity.dsh.pins import verify_launcher_report
from registry.loader import REGISTRY_ROOT, read_runtime_pins, runtime_digest

GOOD = "sha256:" + "a" * 64


def test_lock_pins_the_dsh_requirements() -> None:
    assert read_runtime_pins(REGISTRY_ROOT)["dsh"] == runtime_digest(REGISTRY_ROOT, "dsh")


def test_matching_report_is_accepted() -> None:
    verify_launcher_report({"integrity": "ok", "requirements_digest": GOOD}, GOOD)


@pytest.mark.parametrize(
    "report",
    [
        {"integrity": "ok", "requirements_digest": "sha256:" + "b" * 64},
        {"integrity": "mismatch", "requirements_digest": GOOD, "mismatches": ["bin/runtime"]},
        {"integrity": "error", "detail": "pins.json missing"},
        {},
    ],
)
def test_mismatched_or_tampered_runtime_is_refused(report: dict[str, object]) -> None:
    with pytest.raises(CapabilityError):
        verify_launcher_report(report, GOOD)
