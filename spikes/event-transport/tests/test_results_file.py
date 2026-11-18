"""The suite's results file marks any run that did not run every requirement test
as partial, and records the command as run (impl review F37, round 2 M2)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SPIKE = Path(__file__).resolve().parents[1]


def run_suite(tmp_path: Path, *args: str) -> dict:
    env = {
        **os.environ,
        "SPIKE_TRANSPORTS": "memory",
        "SUITE_HORIZON_S": "2",
        "SPIKE_RESULTS": str(tmp_path),
    }
    subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *args],
        cwd=SPIKE,
        env=env,
        capture_output=True,
        check=False,
    )
    return json.loads((tmp_path / "suite-memory.json").read_text())


@pytest.mark.skipif(os.environ.get("SPIKE_RESULTS") is not None, reason="nested run")
def test_a_full_run_is_not_partial(tmp_path: Path) -> None:
    assert run_suite(tmp_path, "tests/test_suite.py")["partial"] is False


@pytest.mark.skipif(os.environ.get("SPIKE_RESULTS") is not None, reason="nested run")
@pytest.mark.parametrize(
    "selector",
    [
        ["tests/test_suite.py::test_r1_resume"],
        ["tests/test_suite.py", "--deselect", "tests/test_suite.py::test_r7_replay"],
    ],
)
def test_a_subset_run_is_partial_and_records_its_command(
    tmp_path: Path, selector: list[str]
) -> None:
    result = run_suite(tmp_path, *selector)
    assert result["partial"] is True
    assert selector[0] in result["command"]
