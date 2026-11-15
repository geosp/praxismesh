"""DSH launcher in a real container (DSH migration plan D3, ADR-0006, R10, R15, R17).

Runs `infra/dsh/launcher.py` in the pinned Python base image with the DSH container
settings (private cgroup namespace, SYS_ADMIN, no network, read-only root), then
drives it over the control socket as the worker's UID.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import textwrap
import time
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
IMAGE = (
    "python:3.11-slim-bookworm"
    "@sha256:a83ba18aef0f865b1a4a611c2cf460fe446f2795673bbb9fe43be570439e3b39"
)
WORKER = "10001:4243"

CLIENT = textwrap.dedent(
    """
    import json, os, socket, sys
    def ask(f, **req):
        f.write((json.dumps(req) + "\\n").encode()); f.flush()
        return json.loads(f.readline())
    s = socket.socket(socket.AF_UNIX); s.connect("/attempts/.control.sock")
    f = s.makefile("rwb")
    out = {"digests": ask(f, op="digests")}
    tree = "/attempts/task-1/1/1"
    for name in ("home", "workspace", "ipc"):
        os.makedirs(f"{tree}/{name}", exist_ok=True)
    os.makedirs("/attempts/task-2/1/1/workspace", exist_ok=True)
    open("/attempts/task-2/1/1/workspace/secret", "w").write("other attempt")
    open(f"{tree}/home/session.jsonl", "w").write("session")
    out["open"] = ask(f, op="open", attempt="task-1/1/1")
    out["start"] = ask(f, op="start", argv=["sh", "-c", "sleep 60 & sleep 60"])
    import time; time.sleep(0.5)
    out["members"] = ask(f, op="members")
    out["freeze"] = ask(f, op="freeze"); out["thaw"] = ask(f, op="thaw")
    run = lambda c: ask(f, op="exec", command=c, timeout=10)
    out["uid"] = run("id -u")
    out["see_attempts"] = run("ls -A /attempts")
    out["see_session"] = run("cat /attempts/task-1/1/1/home/session.jsonl; ls -A /work")
    out["userns"] = run("unshare -Urm true; echo rc=$?")
    out["caps"] = run("grep CapEff /proc/self/status")
    out["write"] = run("echo hi > /work/out.txt && cat /work/out.txt")
    out["background"] = run("(sleep 60 >/dev/null 2>&1 &) ; echo started")
    out["members_after"] = ask(f, op="members")
    if sys.argv[1] == "stop":
        out["stop"] = ask(f, op="stop", grace=2)
    print(json.dumps(out))
    """
)


def docker(*args: str, check: bool = True, timeout: float = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args], capture_output=True, text=True, check=check, timeout=timeout
    )


@pytest.fixture
def launcher(tmp_path: Path) -> Iterator[str]:
    if shutil.which("docker") is None:
        pytest.skip("docker is not available")
    pins = tmp_path / "pins.json"
    pins.write_text(json.dumps({"files": ["/opt/dsh/launcher.py"]}))
    (tmp_path / "client.py").write_text(CLIENT)
    name = f"dsh-launcher-test-{uuid.uuid4().hex[:8]}"
    docker(
        "run", "-d", "--rm", "--name", name, "--network", "none", "--read-only",
        "--cgroupns=private", "--cap-add=SYS_ADMIN", "--security-opt", "no-new-privileges",
        "--tmpfs", "/tmp", "--tmpfs", "/work", "--tmpfs", "/run",
        "--tmpfs", "/attempts:mode=1770,gid=4243",
        "-v", f"{ROOT / 'infra/dsh/launcher.py'}:/opt/dsh/launcher.py:ro,z",
        "-v", f"{pins}:/opt/dsh/pins.json:ro,z",
        "-v", f"{tmp_path / 'client.py'}:/opt/dsh/client.py:ro,z",
        IMAGE, "python", "/opt/dsh/launcher.py",
    )  # fmt: skip
    try:
        until = time.monotonic() + 20
        while "ready" not in docker("logs", name, check=False).stdout:
            assert time.monotonic() < until, docker("logs", name, check=False).stderr
            time.sleep(0.2)
        yield name
    finally:
        docker("rm", "-f", name, check=False)


def client(name: str, mode: str) -> dict[str, Any]:
    done = docker("exec", "-u", WORKER, name, "python", "/opt/dsh/client.py", mode)
    reply: dict[str, Any] = json.loads(done.stdout.strip().splitlines()[-1])
    return reply


def attempt_state(name: str) -> tuple[str, bool]:
    """Attempt cgroups left, and whether attempt task-1/1/1's tree still exists."""
    cg = docker(
        "exec", name, "find", "/sys/fs/cgroup/attempts", "-mindepth", "1", "-type", "d",
        check=False,
    ).stdout  # fmt: skip
    tree = docker("exec", name, "test", "-e", "/attempts/task-1/1/1", check=False)
    return cg.strip(), tree.returncode == 0


def test_attempt_isolation_and_stop(launcher: str) -> None:
    out = client(launcher, "stop")
    assert "/opt/dsh/launcher.py" in out["digests"]["digests"]
    assert len(out["members"]["members"]) == 3  # sh and both sleeps
    assert out["freeze"] == {"ok": True} and out["thaw"] == {"ok": True}
    assert out["uid"]["stdout"].strip() == "4242"
    assert out["see_attempts"]["stdout"].strip() == ""  # no other attempt, no socket
    assert "session" not in out["see_session"]["stdout"]
    assert "rc=0" not in out["userns"]["stdout"]  # seccomp blocks user namespaces
    assert out["caps"]["stdout"].split()[-1] == "0000000000000000"
    assert out["write"]["stdout"].strip() == "hi"
    assert len(out["members_after"]["members"]) > 3  # the backgrounded sleep stayed in
    assert out["stop"]["processes_left"] == 0 and out["stop"]["tree_removed"]
    assert attempt_state(launcher) == ("", False)


def test_closed_connection_kills_the_attempt(launcher: str) -> None:
    client(launcher, "close")  # exits without stop: the worker died
    until = time.monotonic() + 10
    while attempt_state(launcher)[0] and time.monotonic() < until:
        time.sleep(0.2)
    assert attempt_state(launcher) == ("", False)
    leftover = docker(
        "exec", launcher, "sh", "-c",
        "for c in /proc/[0-9]*/cmdline; do tr '\\0' ' ' < $c; echo; done | grep -c '[s]leep 60'",
        check=False,
    )  # fmt: skip
    assert leftover.stdout.strip() == "0"


def test_restart_reaps_leftover_trees(launcher: str) -> None:
    docker("exec", "-u", WORKER, launcher, "mkdir", "-p", "/attempts/task-9/1/1/workspace")
    docker("exec", "-d", launcher, "python", "/opt/dsh/launcher.py")
    time.sleep(2)
    assert "task-9" not in docker("exec", launcher, "ls", "-A", "/attempts").stdout
