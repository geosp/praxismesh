"""DSH container launcher (DSH migration plan D3, ADR-0006; phase 02 task 1.1).

Runs as root inside the credential-free, network-free DSH container, which holds
CAP_SYS_ADMIN for this process only. Each attempt gets:

- its own cgroup under /sys/fs/cgroup/attempts/, which the worker can freeze, thaw
  and kill through this launcher;
- a private mount namespace showing only its own attempt tree;
- a seccomp filter that blocks new user namespaces (clone/unshare with
  CLONE_NEWUSER; clone3 returns ENOSYS so libc falls back to clone);
- for commands, a separate UID with every capability dropped and no_new_privs.

The worker opens one control connection per attempt on the shared volume's
socket and sends newline-delimited JSON requests. When that connection closes for
any reason (including worker death), the attempt's cgroup is killed and its tree
removed. At start-up the launcher reaps every leftover attempt cgroup and tree.

Standard library only, so the image needs no extra packages.
"""

from __future__ import annotations

import ctypes
import json
import os
import shutil
import socket
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pins

CGROUP = Path("/sys/fs/cgroup")
ATTEMPTS_CG = CGROUP / "attempts"
ATTEMPTS = Path(os.environ.get("DSH_ATTEMPTS", "/attempts"))
CONTROL = Path(os.environ.get("DSH_CONTROL", "/attempts/.control.sock"))
RUNTIME_UID = int(os.environ.get("DSH_RUNTIME_UID", "1000"))
COMMAND_UID = int(os.environ.get("DSH_COMMAND_UID", "4242"))
# The worker, the runtime and commands share this group on the attempt tree;
# directories are setgid and every child runs with umask 0007.
SHARED_GID = int(os.environ.get("DSH_SHARED_GID", "4243"))
WORKER_UID = int(os.environ.get("DSH_WORKER_UID", "10001"))
COMMAND_OUTPUT_CAP = 8000

libc = ctypes.CDLL(None, use_errno=True)
CLONE_NEWNS = 0x00020000
CLONE_NEWUSER = 0x10000000
MS_RDONLY, MS_NOSUID, MS_NODEV, MS_BIND, MS_REC, MS_PRIVATE = 1, 2, 4, 4096, 16384, 1 << 18
PR_SET_NO_NEW_PRIVS, PR_SET_SECCOMP, SECCOMP_MODE_FILTER = 38, 22, 2


def _check(result: int, what: str) -> None:
    if result != 0:
        err = ctypes.get_errno()
        raise OSError(err, f"{what}: {os.strerror(err)}")


def _mount(
    source: str | None, target: str, fstype: str | None, flags: int, data: str | None = None
) -> None:
    _check(
        libc.mount(
            source.encode() if source else None,
            target.encode(),
            fstype.encode() if fstype else None,
            ctypes.c_ulong(flags),
            data.encode() if data else None,
        ),
        f"mount {target}",
    )


# --- seccomp: block new user namespaces (x86-64) ----------------------------------


def _seccomp_program() -> bytes:
    ld, jeq, jge, jset, ret = 0x20, 0x15, 0x35, 0x45, 0x06
    allow, kill = 0x7FFF0000, 0x80000000
    errno = lambda e: 0x00050000 | e  # noqa: E731
    audit_arch_x86_64 = 0xC000003E
    prog = [  # (code, jt, jf, k); jumps are relative to the next instruction
        (ld, 0, 0, 4),  # 0  arch
        (jeq, 1, 0, audit_arch_x86_64),  # 1
        (ret, 0, 0, kill),  # 2  foreign arch
        (ld, 0, 0, 0),  # 3  syscall nr
        (jge, 9, 0, 0x40000000),  # 4  x32 ABI -> 14 kill
        (jeq, 7, 0, 435),  # 5  clone3 -> 13 ENOSYS
        (jeq, 2, 0, 272),  # 6  unshare -> 9
        (jeq, 1, 0, 56),  # 7  clone -> 9
        (ret, 0, 0, allow),  # 8
        (ld, 0, 0, 16),  # 9  args[0], low 32 bits
        (jset, 1, 0, CLONE_NEWUSER),  # 10 -> 12 EPERM
        (ret, 0, 0, allow),  # 11
        (ret, 0, 0, errno(1)),  # 12 EPERM
        (ret, 0, 0, errno(38)),  # 13 ENOSYS
        (ret, 0, 0, kill),  # 14
    ]
    return b"".join(struct.pack("HBBI", *ins) for ins in prog)


_FILTER = ctypes.create_string_buffer(_seccomp_program())


class _SockFprog(ctypes.Structure):
    _fields_ = [("len", ctypes.c_ushort), ("filter", ctypes.c_void_p)]


_FPROG = _SockFprog(len(_FILTER.raw) // 8, ctypes.cast(_FILTER, ctypes.c_void_p))


def install_seccomp() -> None:
    _check(libc.prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0), "no_new_privs")
    _check(libc.prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, ctypes.byref(_FPROG), 0, 0), "seccomp")


# --- per-attempt isolation -----------------------------------------------------------


def _attempt_id(value: str) -> str:
    parts = value.split("/")
    if len(parts) != 3 or not all(
        p and p.replace("-", "").replace("_", "").isalnum() for p in parts
    ):
        raise ValueError("attempt id must be task/turn/attempt")
    return value


def _cgroup_of(attempt: str) -> Path:
    return ATTEMPTS_CG / attempt.replace("/", "__")


def _isolate(attempt: str, view: str) -> None:
    """In the child, before exec: join the attempt cgroup, then enter a private
    mount namespace that shows only this attempt (`view` is where it appears)."""
    (_cgroup_of(attempt) / "cgroup.procs").write_text("0")
    os.umask(0o007)
    _check(libc.unshare(CLONE_NEWNS), "unshare mount namespace")
    _mount(None, "/", None, MS_REC | MS_PRIVATE)
    tree = ATTEMPTS / attempt
    source = tree / ("workspace" if view == "/work" else "")
    os.makedirs(view, exist_ok=True)
    _mount(str(source), view, None, MS_BIND | MS_REC)
    # Hide every attempt tree and the control socket behind an empty tmpfs.
    _mount("none", str(ATTEMPTS), "tmpfs", MS_NOSUID | MS_NODEV, "size=1m,mode=0755")
    os.chdir(view)


def _command_preexec(attempt: str):
    def run() -> None:
        _isolate(attempt, "/work")
        install_seccomp()

    return run


def _runtime_preexec(attempt: str):
    def run() -> None:
        _isolate(attempt, "/run/attempt")
        install_seccomp()

    return run


DROP = [
    "setpriv",
    "--clear-groups",
    "--inh-caps=-all",
    "--bounding-set=-all",
    "--no-new-privs",
]


class Attempt:
    def __init__(self, attempt: str):
        self.id = attempt
        self.cgroup = _cgroup_of(attempt)
        self.runtime: subprocess.Popen | None = None
        self.cgroup.mkdir(parents=True, exist_ok=False)

    def start(self, argv: list[str], env: dict[str, str]) -> int:
        tree = ATTEMPTS / self.id
        for name in ("home", "workspace", "ipc"):
            os.chown(tree / name, RUNTIME_UID, SHARED_GID)
            os.chmod(tree / name, 0o2770)
        self.runtime = subprocess.Popen(
            [*DROP, f"--reuid={RUNTIME_UID}", f"--regid={SHARED_GID}", "--", *argv],
            env={"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": "/run/attempt/home", **env},
            preexec_fn=_runtime_preexec(self.id),
            close_fds=True,
        )
        return self.runtime.pid

    def run_command(self, command: str, timeout: float) -> dict:
        env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": "/work", "LANG": "C.UTF-8"}
        try:
            done = subprocess.run(
                [
                    *DROP,
                    f"--reuid={COMMAND_UID}",
                    f"--regid={SHARED_GID}",
                    "--",
                    "sh",
                    "-c",
                    command,
                ],
                env=env,
                preexec_fn=_command_preexec(self.id),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return {"timed_out": True}
        return {
            "exit": done.returncode,
            "stdout": done.stdout[-COMMAND_OUTPUT_CAP:],
            "stderr": done.stderr[-COMMAND_OUTPUT_CAP // 2 :],
        }

    def freeze(self, frozen: bool, timeout: float = 2.0) -> bool:
        (self.cgroup / "cgroup.freeze").write_text("1" if frozen else "0")
        until = time.monotonic() + timeout
        want = "frozen 1" if frozen else "frozen 0"
        while time.monotonic() < until:
            if want in (self.cgroup / "cgroup.events").read_text():
                return True
            time.sleep(0.01)
        return False

    def members(self) -> list[int]:
        return [int(p) for p in (self.cgroup / "cgroup.procs").read_text().split()]

    def stop(self, grace: float) -> dict:
        """SIGTERM the runtime; kill the whole cgroup when the grace runs out."""
        cooperative = True
        if self.runtime is not None and self.runtime.poll() is None:
            self.runtime.terminate()
            try:
                self.runtime.wait(timeout=grace)
            except subprocess.TimeoutExpired:
                cooperative = False
        return {"cooperative": cooperative, **destroy(self.id)}


def destroy(attempt: str) -> dict:
    cg = _cgroup_of(attempt)
    if cg.exists():
        (cg / "cgroup.freeze").write_text("0")
        (cg / "cgroup.kill").write_text("1")
        until = time.monotonic() + 5
        while (cg / "cgroup.procs").read_text().strip() and time.monotonic() < until:
            time.sleep(0.01)
        left = len((cg / "cgroup.procs").read_text().split())
        if left == 0:
            cg.rmdir()
    else:
        left = 0
    shutil.rmtree(ATTEMPTS / attempt, ignore_errors=True)
    return {"processes_left": left, "tree_removed": not (ATTEMPTS / attempt).exists()}


def reap() -> list[str]:
    """Kill every leftover attempt cgroup and remove every attempt tree."""
    reaped = []
    if ATTEMPTS_CG.exists():
        for cg in sorted(ATTEMPTS_CG.iterdir()):
            if cg.is_dir():
                destroy(cg.name.replace("__", "/"))
                reaped.append(cg.name)
    for task in sorted(p for p in ATTEMPTS.iterdir() if p.is_dir() and not p.name.startswith(".")):
        shutil.rmtree(task, ignore_errors=True)
        reaped.append(task.name)
    return reaped


def digests() -> dict[str, object]:
    """The pinned requirements digest and an integrity check of every installed file
    of the pinned distributions; the worker compares them with the registry lock."""
    try:
        return pins.report()
    except (OSError, ValueError, RuntimeError) as error:
        return {"integrity": "error", "detail": str(error)[:200]}


def setup_cgroups() -> None:
    """cgroup v2 forbids processes in inner nodes: move the launcher into a leaf,
    then delegate controllers to the attempts subtree."""
    _mount(None, str(CGROUP), None, 32)  # MS_REMOUNT without MS_RDONLY: read-write
    (CGROUP / "launcher").mkdir(exist_ok=True)
    (CGROUP / "launcher" / "cgroup.procs").write_text(str(os.getpid()))
    controllers = (CGROUP / "cgroup.controllers").read_text().split()
    (CGROUP / "cgroup.subtree_control").write_text(" ".join("+" + c for c in controllers))
    ATTEMPTS_CG.mkdir(exist_ok=True)
    (ATTEMPTS_CG / "cgroup.subtree_control").write_text(" ".join("+" + c for c in controllers))


def serve_connection(conn: socket.socket) -> None:
    attempt: Attempt | None = None
    stream = conn.makefile("rwb")
    try:
        for line in stream:
            request = json.loads(line)
            op = request.get("op")
            try:
                if op == "digests":
                    reply = {"digests": digests()}
                elif op == "open":
                    attempt = Attempt(_attempt_id(request["attempt"]))
                    reply = {"opened": attempt.id}
                elif attempt is None:
                    raise ValueError("open an attempt first")
                elif op == "start":
                    reply = {"pid": attempt.start(request["argv"], request.get("env", {}))}
                elif op == "exec":
                    reply = attempt.run_command(
                        request["command"], float(request.get("timeout", 60))
                    )
                elif op in ("freeze", "thaw"):
                    reply = {"ok": attempt.freeze(op == "freeze")}
                elif op == "members":
                    reply = {"members": attempt.members()}
                elif op == "poll":
                    code = attempt.runtime.poll() if attempt.runtime else None
                    reply = {"running": code is None and attempt.runtime is not None, "exit": code}
                elif op == "stop":
                    reply = attempt.stop(float(request.get("grace", 5)))
                    attempt = None
                else:
                    raise ValueError(f"unknown op {op!r}")
            except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
                reply = {"error": type(error).__name__, "detail": str(error)[:200]}
            stream.write((json.dumps(reply) + "\n").encode())
            stream.flush()
    finally:
        # The worker's connection is the attempt's lifeline (R10).
        if attempt is not None:
            destroy(attempt.id)
        conn.close()


def main() -> int:
    setup_cgroups()
    reaped = reap()
    CONTROL.unlink(missing_ok=True)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(CONTROL))
    os.chown(CONTROL, WORKER_UID, SHARED_GID)
    os.chmod(CONTROL, 0o600)
    server.listen(4)
    print(json.dumps({"launcher": "ready", "reaped": reaped}), flush=True)
    while True:
        conn, _ = server.accept()
        threading.Thread(target=serve_connection, args=(conn,), daemon=True).start()


if __name__ == "__main__":
    sys.exit(main())
