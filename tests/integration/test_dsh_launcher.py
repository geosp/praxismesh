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

from common.errors import CapabilityError
from harness_activity.dsh.pins import verify_launcher_report
from registry.loader import REGISTRY_ROOT, read_runtime_pins

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
WORKER = "10001:4243"
BINARY = "/opt/dsh/site/deepseek_harness_runtime/runtime/deepseek-harness-sdk-runtime-linux-x64"

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
    if sys.argv[1] == "hold":  # a live attempt a launcher restart must reap
        out["start"] = ask(f, op="start", argv=["sh", "-c", "sleep 60 & sleep 60"])
        import time; time.sleep(30)
        sys.exit(0)
    if sys.argv[1] == "tmp":  # what one attempt leaves in /tmp, the next must not see
        out["write"] = ask(f, op="exec", command="echo leaked > /tmp/marker; echo rc=$?",
                           timeout=10)
        out["stop"] = ask(f, op="stop", grace=2)
        for name in ("home", "workspace", "ipc"):
            os.makedirs(f"/attempts/task-3/1/1/{name}", exist_ok=True)
        out["open2"] = ask(f, op="open", attempt="task-3/1/1")
        read = "cat /tmp/marker 2>/dev/null; echo rc=$?; ls -A /tmp"
        out["read"] = ask(f, op="exec", command=read, timeout=10)
        out["stop2"] = ask(f, op="stop", grace=2)
        print(json.dumps(out)); sys.exit(0)
    if sys.argv[1] == "frozen-stop":  # a stop while a barrier holds the freeze
        handler = ("import signal,sys,time; "
                   "signal.signal(signal.SIGTERM, lambda *a: sys.exit(0)); time.sleep(60)")
        out["start"] = ask(f, op="start", argv=["python", "-c", handler])
        import time; time.sleep(0.5)
        out["freeze"] = ask(f, op="freeze")
        out["stop"] = ask(f, op="stop", grace=2)
        print(json.dumps(out)); sys.exit(0)
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
    out["cgroup_escape"] = run("echo $$ > /sys/fs/cgroup/cgroup.procs; echo rc=$?")
    out["mount"] = run("mount -t tmpfs none /work; echo rc=$?")
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


@pytest.fixture(scope="module")
def image() -> str:
    if shutil.which("docker") is None:
        pytest.skip("docker is not available")
    built = docker("build", "-q", "-f", str(ROOT / "infra/dsh/Dockerfile"), str(ROOT / "infra/dsh"),
                   timeout=900)  # fmt: skip
    return built.stdout.strip()


def start_launcher(image: str, tmp_path: Path, *extra: str) -> str:
    (tmp_path / "client.py").write_text(CLIENT)
    name = f"dsh-launcher-test-{uuid.uuid4().hex[:8]}"
    docker(
        "run", "-d", "--rm", "--name", name, "--network", "none", "--read-only",
        "--cgroupns=private", "--cap-add=SYS_ADMIN",
        "--security-opt", "no-new-privileges", "--security-opt", "apparmor=unconfined",
        "--tmpfs", "/tmp", "--tmpfs", "/work", "--tmpfs", "/run",
        "--tmpfs", "/attempts:mode=1770,gid=4243",
        "-v", f"{tmp_path / 'client.py'}:/opt/dsh/client.py:ro,z", *extra, image,
    )  # fmt: skip
    until = time.monotonic() + 20
    while "ready" not in docker("logs", name, check=False).stdout:
        assert time.monotonic() < until, docker("logs", name, check=False).stderr
        time.sleep(0.2)
    return name


@pytest.fixture
def launcher(image: str, tmp_path: Path) -> Iterator[str]:
    name = start_launcher(image, tmp_path)
    try:
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
    verify_launcher_report(out["digests"]["digests"], read_runtime_pins(REGISTRY_ROOT)["dsh"])
    assert len(out["members"]["members"]) == 3  # sh and both sleeps
    assert out["freeze"] == {"ok": True} and out["thaw"] == {"ok": True}
    assert out["uid"]["stdout"].strip() == "4242"
    assert out["see_attempts"]["stdout"].strip() == ""  # no other attempt, no socket
    assert "session" not in out["see_session"]["stdout"]
    assert "rc=0" not in out["userns"]["stdout"]  # seccomp blocks user namespaces
    assert out["caps"]["stdout"].split()[-1] == "0000000000000000"
    assert out["write"]["stdout"].strip() == "hi"
    # The isolation probe's command checks, through the real launcher path:
    assert "rc=0" not in out["cgroup_escape"]["stdout"]
    assert "rc=0" not in out["mount"]["stdout"]
    assert len(out["members_after"]["members"]) > 3  # the backgrounded sleep stayed in
    assert out["stop"]["processes_left"] == 0 and out["stop"]["tree_removed"]
    assert attempt_state(launcher) == ("", False)


def test_stop_while_frozen_is_cooperative(launcher: str) -> None:
    """R8, R9, D6 (review F60): a frozen runtime cannot run its SIGTERM handler, so
    the launcher thaws it first; a runtime that exits on SIGTERM is a cooperative stop."""
    out = client(launcher, "frozen-stop")
    assert out["freeze"] == {"ok": True}
    assert out["stop"]["cooperative"] is True
    assert out["stop"]["processes_left"] == 0 and out["stop"]["tree_removed"]
    assert attempt_state(launcher) == ("", False)


def test_commands_get_their_own_tmp(launcher: str) -> None:
    """R15 (review F63): a command's /tmp belongs to its attempt; what a command of
    one attempt writes there is gone for the next attempt, of any task."""
    out = client(launcher, "tmp")
    assert "rc=0" in out["write"]["stdout"]
    assert out["read"]["stdout"].split() == ["rc=1"]  # no marker, and /tmp is empty
    assert docker("exec", launcher, "ls", "-A", "/tmp").stdout.strip() == ""
    assert attempt_state(launcher) == ("", False)


def test_closed_connection_kills_the_attempt(launcher: str) -> None:
    client(launcher, "close")  # exits without stop: the worker died
    until = time.monotonic() + 10
    while attempt_state(launcher)[0] and time.monotonic() < until:
        time.sleep(0.2)
    assert attempt_state(launcher) == ("", False)
    assert "task-1" not in docker("exec", launcher, "ls", "-A", "/attempts").stdout
    leftover = docker(
        "exec", launcher, "sh", "-c",
        "for c in /proc/[0-9]*/cmdline; do tr '\\0' ' ' < $c; echo; done | grep -c '[s]leep 60'",
        check=False,
    )  # fmt: skip
    assert leftover.stdout.strip() == "0"


def sleepers(name: str) -> str:
    return docker(
        "exec", name, "sh", "-c",
        "for c in /proc/[0-9]*/cmdline; do tr '\\0' ' ' < $c; echo; done | grep -c '[s]leep 60'",
        check=False,
    ).stdout.strip()  # fmt: skip


def test_restart_reaps_leftover_attempts(launcher: str) -> None:
    """Task 1.1 (review F94): a launcher starting up kills every leftover attempt's
    processes, removes its cgroup and removes every leftover tree."""
    docker("exec", "-u", WORKER, launcher, "mkdir", "-p", "/attempts/task-9/1/1/workspace")
    docker("exec", "-d", "-u", WORKER, launcher, "python", "/opt/dsh/client.py", "hold")
    until = time.monotonic() + 10
    while int(sleepers(launcher) or 0) < 2:
        assert time.monotonic() < until
        time.sleep(0.2)
    assert attempt_state(launcher)[0]  # a live attempt cgroup
    docker("exec", "-d", launcher, "python", "/opt/dsh/launcher.py")  # the restart
    until = time.monotonic() + 10
    while (attempt_state(launcher) != ("", False) or sleepers(launcher) != "0") and (
        time.monotonic() < until
    ):
        time.sleep(0.2)
    assert attempt_state(launcher) == ("", False)
    assert sleepers(launcher) == "0"
    assert "task-9" not in docker("exec", launcher, "ls", "-A", "/attempts").stdout


def test_tampered_runtime_is_reported_and_refused(image: str, tmp_path: Path) -> None:
    """R17: a changed native binary fails the integrity check the worker relies on."""
    fake = tmp_path / "fake-runtime"
    fake.write_bytes(b"not the pinned binary")
    name = start_launcher(image, tmp_path, "-v", f"{fake}:{BINARY}:ro,z")
    try:
        report = client(name, "close")["digests"]["digests"]
    finally:
        docker("rm", "-f", name, check=False)
    assert report["integrity"] == "mismatch"
    with pytest.raises(CapabilityError, match="integrity"):
        verify_launcher_report(report, read_runtime_pins(REGISTRY_ROOT)["dsh"])
