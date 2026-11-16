"""DSH runtime pins: lock and image agree, and the worker refuses a mismatch (R17)."""

from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path

import pytest

from common.errors import CapabilityError
from harness_activity.dsh.pins import verify_launcher_report
from registry.loader import REGISTRY_ROOT, read_runtime_pins, runtime_digest

GOOD = "sha256:" + "a" * 64
DSH = Path(__file__).resolve().parents[1] / "infra" / "dsh"


def test_lock_pins_the_dsh_requirements() -> None:
    assert read_runtime_pins(REGISTRY_ROOT)["dsh"] == runtime_digest(REGISTRY_ROOT, "dsh")


def test_control_files_are_part_of_the_pin(tmp_path: Path) -> None:
    """R17 (review F92): an image whose launcher differs does not match the lock."""
    spec = importlib.util.spec_from_file_location("dsh_pins", DSH / "pins.py")
    assert spec is not None and spec.loader is not None
    pins = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pins)
    for name in pins.CONTROL_FILES:
        shutil.copy(DSH / name, tmp_path / name)
    same = pins.runtime_digest(GOOD, tmp_path)
    assert same == pins.runtime_digest(GOOD, DSH)
    (tmp_path / "launcher.py").write_text("# an older launcher without seccomp\n")
    assert pins.runtime_digest(GOOD, tmp_path) != same


def test_matching_report_is_accepted() -> None:
    verify_launcher_report({"integrity": "ok", "runtime_digest": GOOD}, GOOD)


@pytest.mark.parametrize(
    "report",
    [
        {"integrity": "ok", "runtime_digest": "sha256:" + "b" * 64},
        # The requirements alone match, but the control files differ (review F92).
        {"integrity": "ok", "requirements_digest": GOOD, "runtime_digest": "sha256:" + "c" * 64},
        {"integrity": "mismatch", "runtime_digest": GOOD, "mismatches": ["bin/runtime"]},
        {"integrity": "error", "detail": "pins.json missing"},
        {},
    ],
)
def test_mismatched_or_tampered_runtime_is_refused(report: dict[str, object]) -> None:
    with pytest.raises(CapabilityError):
        verify_launcher_report(report, GOOD)
