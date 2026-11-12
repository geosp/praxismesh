"""Workers as real host processes, for the recovery tests (RFC: Recovery check).

Each worker runs `python -m workers.main` in its own process group, so a test can
SIGKILL a worker and its MCP subprocesses, which is what a lost container looks
like to Temporal: the heartbeats stop. The tests use a generated registry (a copy
of registry/ with a short heartbeat timeout and the sample server's test pause).
"""

from __future__ import annotations

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
        proc = self.procs[name]
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait(timeout=10)

    def stop_all(self) -> None:
        for proc in self.procs.values():
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait(timeout=10)


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
