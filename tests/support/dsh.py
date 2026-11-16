"""A DSH container for integration tests (DSH migration plan D3, ADR-0006).

Builds `infra/dsh/Dockerfile` and runs it with the settings of the Compose service
`dsh-a` (no network, read-only root, private cgroup namespace, SYS_ADMIN for the
launcher only). The attempt volume is a host directory, so the test process plays
the worker: the launcher is told the test's UID and group instead of the worker
image's, and a runtime UID that differs from both.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import pytest

from common.blob_store import MemoryBlobStore
from harness_activity.dsh.runner import DshRunner
from harness_activity.events import EventSink

ROOT = Path(__file__).resolve().parents[2]
# Never the test's own UID: as in Compose, the worker reaches the runtime's files
# only through the shared group.
RUNTIME_UID = 4241 if os.getuid() != 4241 else 4240


def docker(*args: str, check: bool = True, timeout: float = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args], capture_output=True, text=True, check=check, timeout=timeout
    )


def build_image() -> str:
    if shutil.which("docker") is None:
        pytest.skip("docker is not available")
    built = docker(
        "build", "-q", "-f", str(ROOT / "infra/dsh/Dockerfile"), str(ROOT / "infra/dsh"),
        timeout=900,
    )  # fmt: skip
    return built.stdout.strip()


class MemoryLedgerStore:
    """A `LedgerStore` for tests that need no database."""

    def __init__(self) -> None:
        self.rows: dict[tuple[str, int, int, str], tuple[int, int] | None] = {}

    async def dispatch(
        self, task_id: str, turn: int, attempt: int, request_id: str, purpose: str
    ) -> None:
        self.rows[(task_id, turn, attempt, request_id)] = None

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
        return DshRunner(self.control, MemoryLedgerStore(), MemoryBlobStore(), sink)

    def exec(self, *command: str) -> subprocess.CompletedProcess[str]:
        return docker("exec", self.name, *command, check=False)

    def attempt_cgroups(self) -> list[str]:
        found = self.exec(
            "find", "/sys/fs/cgroup/attempts", "-mindepth", "1", "-maxdepth", "1", "-type", "d"
        )
        return found.stdout.split()

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
        "--cgroupns=private", "--cap-add=SYS_ADMIN", "--security-opt", "no-new-privileges",
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
