"""Each DSH worker pair has an attempt volume no other service mounts, and
`default` has two pairs (DSH migration plan D3, ADR-0006, notes.md#rollout)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

COMPOSE = Path(__file__).resolve().parents[1] / "infra" / "docker-compose.yml"


def services() -> dict[str, Any]:
    return dict(yaml.safe_load(COMPOSE.read_text())["services"])


def mounts(service: dict[str, Any]) -> set[str]:
    return {v.split(":", 1)[0] for v in service.get("volumes", []) if isinstance(v, str)}


def test_each_dsh_pair_has_its_own_attempt_volume() -> None:
    found = services()
    pairs = sorted(name.removeprefix("worker-") for name in found if name.startswith("worker-dsh-"))
    assert pairs == ["dsh-a", "dsh-b"]
    for dsh in pairs:
        worker = found[f"worker-{dsh}"]
        volume = f"dsh-attempts-{dsh.removeprefix('dsh-')}"
        assert mounts(found[dsh]) == mounts(worker) == {volume}
        assert worker["command"] == ["template", "local-dsh"]
        assert worker["environment"]["DSH_CONTROL"] == "/attempts/.control.sock"
        others = [n for n, s in found.items() if n not in (dsh, f"worker-{dsh}")]
        assert not [n for n in others if volume in mounts(found[n])]
        assert found[dsh]["network_mode"] == "none" and found[dsh]["read_only"] is True


def test_dsh_pairs_share_their_isolation_settings() -> None:
    """F181: the second pair keeps the first pair's container settings (D3)."""
    found = services()
    keys = ("network_mode", "read_only", "cgroup", "cap_add", "security_opt", "tmpfs")
    assert {k: found["dsh-a"].get(k) for k in keys} == {k: found["dsh-b"].get(k) for k in keys}
    assert found["dsh-a"]["environment"] == found["dsh-b"]["environment"]
    for worker in ("worker-dsh-a", "worker-dsh-b"):
        assert found[worker]["group_add"] == ["4243"]
