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
RESULTS = Path(os.environ.get("SPIKE_RESULTS", SPIKE / "results"))
_outcomes: dict[str, dict[str, str]] = {}
_ran: dict[str, set[str]] = {}  # option -> requirement tests that reported


def _expected() -> set[str]:
    """Every requirement test in tests/test_suite.py: a run missing any is partial."""
    import ast

    tree = ast.parse((SPIKE / "tests" / "test_suite.py").read_text())
    return {
        n.name
        for n in tree.body
        if isinstance(n, ast.AsyncFunctionDef | ast.FunctionDef)
        and any("requirement" in ast.unparse(d) for d in n.decorator_list)
    }


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "requirement(rid): the plan requirement a test checks")


def _names() -> list[str]:
    return [n for n in os.environ.get("SPIKE_TRANSPORTS", "memory").split(",") if n]


@pytest.fixture
def horizon_s() -> float:
    return float(os.environ.get("SUITE_HORIZON_S", "60"))


@pytest.fixture(params=_names())
def option_name(request: pytest.FixtureRequest) -> str:
    return str(request.param)


@pytest.fixture
async def transport(option_name: str, horizon_s: float) -> AsyncIterator[EventTransport]:
    built = await OPTIONS[option_name].build(horizon_s)
    try:
        yield built
    finally:
        await built.close()


_RANK = {"pass": 0, "n/a": 0, "error": 1, "fail": 2}


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[Any]) -> Any:
    report = yield
    marker = item.get_closest_marker("requirement")
    callspec = getattr(item, "callspec", None)
    if marker is None or callspec is None or "option_name" not in callspec.params:
        return report
    name, rid = callspec.params["option_name"], marker.args[0]
    if report.when == "call" or (report.when == "setup" and (report.failed or report.skipped)):
        _ran.setdefault(name, set()).add(item.originalname)
    if rid == "R4" and not OPTIONS[name].hosted:
        outcome = "n/a"  # no Workflow to roll over: counts as passed (plan D2)
    elif report.when == "setup" and report.failed:
        outcome = "error"  # the stack or the transport could not be built
    elif report.when == "call":
        outcome = "fail" if report.failed else "pass"
    elif report.skipped and report.when == "setup":
        outcome = "n/a"
    else:
        return report
    recorded = _outcomes.setdefault(name, {})
    if _RANK[outcome] >= _RANK.get(recorded.get(rid, "pass"), 0) or rid not in recorded:
        recorded[rid] = outcome  # a requirement with several tests keeps its worst outcome
    return report


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, cwd=SPIKE).stdout.strip()


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    if not _outcomes:
        return
    expected = _expected()
    args = " ".join(sys.argv[1:])
    RESULTS.mkdir(exist_ok=True)
    for name, outcomes in _outcomes.items():
        (RESULTS / f"suite-{name}.json").write_text(
            json.dumps(
                {
                    "transport": name,
                    "commit": _git("rev-parse", "HEAD"),
                    "dirty": bool(_git("status", "--porcelain", "--", ".", ":!results")),
                    "command": f"SPIKE_TRANSPORTS={os.environ.get('SPIKE_TRANSPORTS', 'memory')} "
                    f"SUITE_HORIZON_S={os.environ.get('SUITE_HORIZON_S', '60')} pytest {args}",
                    "partial": _ran.get(name, set()) != expected or exitstatus not in (0, 1),
                    "finished": datetime.now(UTC).isoformat(timespec="seconds"),
                    "requirements": dict(sorted(outcomes.items())),
                },
                indent=2,
            )
            + "\n"
        )
