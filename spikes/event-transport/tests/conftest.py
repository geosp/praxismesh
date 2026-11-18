"""Suite fixtures and the results file (task 1.4).

`SPIKE_TRANSPORTS` (default `memory`) picks the transports; each test that uses the
`transport` fixture runs once per transport. Outcomes of tests marked
`requirement("Rn")` are written to `results/suite-<transport>.json` with the
commit and command that produced them (R8).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from event_transport.factories import OPTIONS
from event_transport.transport import EventTransport

SPIKE = Path(__file__).resolve().parents[1]
RESULTS = SPIKE / "results"
_outcomes: dict[str, dict[str, str]] = {}


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "requirement(rid): the plan requirement a test checks")


def _names() -> list[str]:
    return [n for n in os.environ.get("SPIKE_TRANSPORTS", "memory").split(",") if n]


@pytest.fixture
def horizon_s() -> float:
    return float(os.environ.get("SUITE_HORIZON_S", "60"))


@pytest.fixture(params=_names())
async def transport(
    request: pytest.FixtureRequest, horizon_s: float
) -> AsyncIterator[EventTransport]:
    option = OPTIONS[request.param]
    built = await option.build(horizon_s)
    try:
        yield built
    finally:
        await built.close()


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[Any]) -> Any:
    report = yield
    marker = item.get_closest_marker("requirement")
    callspec = getattr(item, "callspec", None)
    if marker is None or callspec is None or "transport" not in callspec.params:
        return report
    name = callspec.params["transport"]
    rid = marker.args[0]
    if report.when == "call" or (report.when == "setup" and report.failed):
        outcome = "pass" if report.passed else "fail"
        if outcome == "pass" and rid == "R4" and not OPTIONS[name].hosted:
            outcome = "n/a"
        _outcomes.setdefault(name, {})[rid] = outcome
    return report


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    if not _outcomes:
        return
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=SPIKE
    ).stdout.strip()
    RESULTS.mkdir(exist_ok=True)
    for name, outcomes in _outcomes.items():
        (RESULTS / f"suite-{name}.json").write_text(
            json.dumps(
                {
                    "transport": name,
                    "commit": commit,
                    "command": " ".join(["SPIKE_TRANSPORTS=" + name, *sys.argv]),
                    "finished": datetime.now(UTC).isoformat(timespec="seconds"),
                    "requirements": dict(sorted(outcomes.items())),
                },
                indent=2,
            )
            + "\n"
        )
