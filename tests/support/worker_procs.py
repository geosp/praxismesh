"""Workers as real host processes, for the recovery tests (RFC: Recovery check).

Each worker runs `python -m workers.main`. A test can SIGKILL a worker and every
process below it (MCP servers included), which is what a lost container looks
like to Temporal: the heartbeats stop. It can also SIGSTOP and SIGCONT one, to
bring a superseded attempt back. The tests use a generated registry (a copy
of registry/ with a short heartbeat timeout and the sample server's test pause).
"""

from __future__ import annotations

import contextlib
import os
import shutil
import signal
import subprocess
import sys
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from registry.loader import REGISTRY_ROOT
from registry.lock import update

ROOT = Path(__file__).resolve().parents[2]


def make_test_registry(target: Path, pause_file: Path) -> Path:
    """A registry copy: 5 s heartbeat timeout, and the sample server's test pause
    (`SAMPLE_MCP_PAUSE_FILE`, through its literal `env`) with a session timeout
    longer than any hold."""
    shutil.copytree(REGISTRY_ROOT, target, ignore=shutil.ignore_patterns("*.py", "__pycache__"))
    template = target / "templates" / "local-default.yaml"
    data = yaml.safe_load(template.read_text())
    data["heartbeat_timeout"] = "PT5S"
    template.write_text(yaml.safe_dump(data, sort_keys=False))
    server = target / "mcp" / "sample-shop.yaml"
    entry = yaml.safe_load(server.read_text())
    entry["env"] = {"SAMPLE_MCP_PAUSE_FILE": str(pause_file)}
    entry["client_session_timeout_seconds"] = 600
    server.write_text(yaml.safe_dump(entry, sort_keys=False))
    (target / "registry.lock").unlink()
    assert update(target, check=False) == []
    return target


def descendants(pid: int) -> list[int]:
    """Every process below `pid`, from /proc (Linux; the recovery tests' host)."""
    children: dict[int, list[int]] = {}
    for stat in Path("/proc").glob("[0-9]*/stat"):
        with contextlib.suppress(OSError, ValueError, IndexError):
            fields = stat.read_text().rsplit(")", 1)[1].split()
            children.setdefault(int(fields[1]), []).append(int(stat.parent.name))
    found, queue = [], [pid]
    while queue:
        for child in children.get(queue.pop(), []):
            found.append(child)
            queue.append(child)
    return found


@dataclass
class WorkerProcs:
    env: dict[str, str] = field(repr=False)  # holds credentials: never print it
    procs: dict[str, subprocess.Popen[bytes]] = field(default_factory=dict)

    def start(self, name: str, *args: str) -> None:
        log = open(Path(self.env["PRAXIS_SCRATCH"]) / f"{name}.log", "wb")  # noqa: SIM115
        self.procs[name] = subprocess.Popen(
            [sys.executable, "-m", "workers.main", *args],
            cwd=ROOT,
            env={**self.env, "PRAXIS_SCRATCH": str(Path(self.env["PRAXIS_SCRATCH"]) / name)},
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    def pid_of(self, identity: str) -> int:
        """The PID in a worker identity, `<host>@<pid>/<template>`."""
        return int(identity.split("@", 1)[1].split("/", 1)[0])

    def name_of(self, pid: int) -> str:
        return next(name for name, p in self.procs.items() if p.pid == pid)

    def kill(self, name: str) -> None:
        """SIGKILL a worker and every process it started. The MCP stdio client
        starts servers in their own session, so the process group alone would
        miss them (informal review F9)."""
        proc = self.procs[name]
        for pid in [*descendants(proc.pid), proc.pid]:
            with contextlib.suppress(ProcessLookupError):
                os.kill(pid, signal.SIGKILL)
        proc.wait(timeout=10)

    def stop(self, name: str) -> None:
        """SIGSTOP a worker and its children: it freezes, then may come back."""
        for pid in [self.procs[name].pid, *descendants(self.procs[name].pid)]:
            with contextlib.suppress(ProcessLookupError):
                os.kill(pid, signal.SIGSTOP)

    def resume(self, name: str) -> None:
        for pid in [self.procs[name].pid, *descendants(self.procs[name].pid)]:
            with contextlib.suppress(ProcessLookupError):
                os.kill(pid, signal.SIGCONT)

    def stop_all(self) -> None:
        for name, proc in self.procs.items():
            if proc.poll() is None:
                self.kill(name)


@contextmanager
def worker_processes(scratch: Path, model_url: str, registry: Path) -> Iterator[WorkerProcs]:
    env = {
        **os.environ,
        "PRAXIS_SCRATCH": str(scratch),
        "PRAXIS_QUEUE_PREFIX": f"recovery-{uuid.uuid4().hex[:8]}.",
        "PRAXIS_REGISTRY": str(registry),
        "VLLM_BASE_URL": model_url,
        "LOG_LEVEL": "INFO",
    }
    env.pop("METRICS_PORT", None)
    scratch.mkdir(parents=True, exist_ok=True)
    workers = WorkerProcs(env)
    try:
        workers.start("orchestrator", "orchestrator")
        workers.start("worker-a", "template", "local-default")
        workers.start("worker-b", "template", "local-default")
        time.sleep(3)
        for name, proc in workers.procs.items():
            if proc.poll() is not None:
                log = (scratch / f"{name}.log").read_text()[-2000:]
                raise RuntimeError(f"{name} exited at startup:\n{log}")
        yield workers
    finally:
        workers.stop_all()
