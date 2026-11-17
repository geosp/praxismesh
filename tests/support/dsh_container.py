"""A paired DSH container outside Compose, for integration tests and the agent
benchmark (DSH migration plan D3, D5; ADR-0006). No pytest here: `make benchmark`
imports it too.

Builds `infra/dsh/Dockerfile` and runs it with the settings of the Compose service
`dsh-a` (no network, read-only root, private cgroup namespace, SYS_ADMIN for the
launcher only). The attempt volume is a host directory, so the calling process plays
the worker: the launcher is told the caller's UID and group instead of the worker
image's, and a runtime UID that differs from both.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from common.blob_store import MemoryBlobStore
from harness_activity.dsh.runner import DshRunner
from harness_activity.events import EventSink
from registry.loader import REGISTRY_ROOT, read_runtime_pins

ROOT = Path(__file__).resolve().parents[2]
# Never the caller's own UID: as in Compose, the worker reaches the runtime's files
# only through the shared group.
RUNTIME_UID = 4241 if os.getuid() != 4241 else 4240


# Every alive (non-zombie) process in the container that is not root's: the
# launcher and `docker exec` are root, the DSH runtime and commands never are.
ATTEMPT_PROCESSES = """
import os
for pid in filter(str.isdigit, os.listdir("/proc")):
    try:
        if os.stat(f"/proc/{pid}").st_uid:
            state = open(f"/proc/{pid}/stat").read().rsplit(")", 1)[1].split()[0]
            if state != "Z":
                print(pid, open(f"/proc/{pid}/cmdline").read().replace(chr(0), " "))
    except OSError:
        pass
"""


def docker(*args: str, check: bool = True, timeout: float = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args], capture_output=True, text=True, check=check, timeout=timeout
    )


def build_image() -> str:
    """Build the DSH image and return its ID. Raises when docker is missing."""
    if shutil.which("docker") is None:
        raise RuntimeError("docker is not available")
    built = docker(
        "build", "-q", "-f", str(ROOT / "infra/dsh/Dockerfile"), str(ROOT / "infra/dsh"),
        timeout=900,
    )  # fmt: skip
    return built.stdout.strip()


class MemoryLedgerStore:
    """A `LedgerStore` for tests that need no database."""

    def __init__(self) -> None:
        self.rows: dict[tuple[str, int, int, str], tuple[int, int] | None] = {}
        self.superseded = False  # a newer attempt exists: the fence refuses

    async def dispatch(
        self, task_id: str, turn: int, attempt: int, request_id: str, purpose: str
    ) -> bool:
        if self.superseded:
            return False
        self.rows[(task_id, turn, attempt, request_id)] = None
        return True

    async def settle(
        self,
        task_id: str,
        turn: int,
        attempt: int,
        request_id: str,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        self.rows[(task_id, turn, attempt, request_id)] = (input_tokens, output_tokens)


@dataclass
class DshContainer:
    name: str
    attempts: Path  # the attempt volume, as the test process sees it

    @property
    def control(self) -> Path:
        return self.attempts / ".control.sock"

    def workspace(self, task: str | None = None, turn: int = 1, attempt: int = 1) -> Path:
        """A new attempt's workspace directory."""
        path = self.attempts / (task or f"t-{uuid.uuid4().hex[:10]}") / str(turn) / str(attempt)
        (path / "workspace").mkdir(parents=True)
        return path / "workspace"

    def runner(self, sink: EventSink | None = None) -> DshRunner:
        # Every attempt checks the pin, as a worker's does (R17).
        pinned = read_runtime_pins(REGISTRY_ROOT)["dsh"]
        return DshRunner(self.control, MemoryLedgerStore(), MemoryBlobStore(), sink, pinned=pinned)

    def exec(self, *command: str) -> subprocess.CompletedProcess[str]:
        return docker("exec", self.name, *command, check=False)

    def attempt_cgroups(self) -> list[str]:
        found = self.exec(
            "find", "/sys/fs/cgroup/attempts", "-mindepth", "1", "-maxdepth", "1", "-type", "d"
        )
        return found.stdout.split()

    def attempt_processes(self) -> list[str]:
        """The DSH runtime and command processes alive in the container."""
        found = self.exec("python", "-c", ATTEMPT_PROCESSES)
        assert found.returncode == 0, found.stderr
        return found.stdout.splitlines()

    def attempt_trees(self) -> list[str]:
        return sorted(p.name for p in self.attempts.iterdir() if p.name != ".control.sock")

    def leftovers(self) -> dict[str, list[str]]:
        """What attempts left behind: cgroups, processes and trees. Empty when clean."""
        found = {
            "cgroups": self.attempt_cgroups(),
            "processes": self.attempt_processes(),
            "trees": self.attempt_trees(),
        }
        return {kind: items for kind, items in found.items() if items}

    async def stays_clean(self, seconds: float, interval: float = 0.5) -> dict[str, list[str]]:
        """Watch for `seconds` (R8's observation window): the first leftovers seen,
        or nothing."""
        until = time.monotonic() + seconds
        while time.monotonic() < until:
            if found := await asyncio.to_thread(self.leftovers):
                return found
            await asyncio.sleep(interval)
        return await asyncio.to_thread(self.leftovers)

    def stop(self) -> None:
        docker("rm", "-f", self.name, check=False)
        # Whatever the container's UIDs left behind is removed as them.
        docker(
            "run", "--rm", "--network", "none", "-v", f"{self.attempts}:/attempts",
            "python:3.11-slim-bookworm", "sh", "-c", "rm -rf /attempts/* /attempts/.control.sock",
            check=False,
        )  # fmt: skip
        shutil.rmtree(self.attempts, ignore_errors=True)


def start_container(image: str) -> DshContainer:
    # A short path: Unix socket addresses are limited to about 100 bytes.
    attempts = Path(tempfile.mkdtemp(prefix="dsh-", dir="/tmp"))
    attempts.chmod(0o770)
    name = f"dsh-test-{uuid.uuid4().hex[:8]}"
    docker(
        "run", "-d", "--name", name, "--network", "none", "--read-only",
        "--cgroupns=private", "--cap-add=SYS_ADMIN",
        "--security-opt", "no-new-privileges", "--security-opt", "apparmor=unconfined",
        "--tmpfs", "/tmp", "--tmpfs", "/work", "--tmpfs", "/run",
        "-v", f"{attempts}:/attempts",
        "-e", f"DSH_WORKER_UID={os.getuid()}", "-e", f"DSH_SHARED_GID={os.getgid()}",
        "-e", f"DSH_RUNTIME_UID={RUNTIME_UID}",
        image,
    )  # fmt: skip
    container = DshContainer(name, attempts)
    until = time.monotonic() + 30
    while not container.control.exists():
        if time.monotonic() > until:
            logs = docker("logs", name, check=False)
            container.stop()
            raise AssertionError(f"the DSH launcher did not start: {logs.stdout} {logs.stderr}")
        time.sleep(0.1)
    return container
