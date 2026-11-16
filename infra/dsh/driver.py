"""DSH runtime entry point for one attempt (DSH migration plan D3, R14).

The launcher starts this as the runtime UID inside the attempt's cgroup and mount
view, where the attempt tree is `/run/attempt`. It reads the worker's files in
`config/`, runs one DSH session turn and writes `ipc/result.json`.

The container has no network. The DSH model provider talks to a loopback relay
in this process, which forwards only the model paths to the worker's gateway
socket in the attempt tree. Commands share the loopback interface, so the relay
passes the per-attempt key through and the gateway checks it.

DSH keeps its session directory private to its own UID, and the worker captures
it as a member of the attempt's group. The relay therefore opens the session
files to that group before it forwards a model request (DSH has flushed the
earlier tool results by then, plan D6), and again when the run ends. If that
did not happen, the worker's barrier fails and no checkpoint is written.

Standard library and the pinned DSH SDK only.
"""

from __future__ import annotations

import http.client
import http.server
import json
import os
import signal
import socket
import threading
from pathlib import Path

TREE = Path("/run/attempt")
HOME = TREE / "home"
GATEWAY = TREE / "ipc/gateway.sock"
MAX_BODY = 8 * 1024 * 1024
MODEL_PATHS = {"/v1/chat/completions", "/v1/models"}
SESSION = "task"


def share_home() -> None:
    """Let the attempt's group read what this UID owns under DSH's home."""
    for root, directories, files in os.walk(HOME):
        for name, bits in [(d, 0o050) for d in directories] + [(f, 0o040) for f in files]:
            path = os.path.join(root, name)
            try:
                mode = os.lstat(path).st_mode
                if not os.path.islink(path) and mode & bits != bits:
                    os.chmod(path, (mode & 0o7777) | bits)
            except OSError:
                pass  # not ours (restored by the worker, already shared), or gone


def serve_relay(port: int) -> http.server.ThreadingHTTPServer:
    class Relay(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            self.forward()

        def do_GET(self) -> None:
            self.forward()

        def forward(self) -> None:
            size = int(self.headers.get("Content-Length", "0"))
            if self.path not in MODEL_PATHS or not 0 <= size <= MAX_BODY:
                self.send_error(403)
                return
            share_home()
            connection = http.client.HTTPConnection("gateway", timeout=660)
            connection.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            connection.sock.settimeout(660)
            try:
                connection.sock.connect(str(GATEWAY))
                connection.request(
                    self.command,
                    self.path,
                    self.rfile.read(size),
                    {
                        "Content-Type": "application/json",
                        "Authorization": self.headers.get("Authorization", ""),
                    },
                )
                response = connection.getresponse()
                body = response.read()
                self.send_response(response.status)
                self.send_header(
                    "Content-Type", response.getheader("Content-Type", "application/json")
                )
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except OSError:
                self.send_error(502)
            finally:
                connection.close()

        def log_message(self, *args: object) -> None:
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), Relay)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def main() -> None:
    from deepseek_harness import DeepSeekHarness

    config = json.loads((TREE / "config/input.json").read_text())
    relay = serve_relay(config["relay_port"])
    harness = DeepSeekHarness(
        dsh_home=str(HOME),
        cwd=str(TREE / "workspace"),
        runtime_cwd=str(TREE / "workspace"),
        profile="sdk-minimal",
        provider="praxis-local",
        model=config["model"],
        patches=(str(TREE / "config/composition.yaml"),),
        initialize_timeout_seconds=25,
        request_timeout_seconds=config["request_timeout_seconds"],
        shutdown_timeout_seconds=1,
        max_tokens=config["max_tokens"],
    )
    # A cooperative stop (R8): SIGTERM closes the runtime, which ends the run.
    signal.signal(signal.SIGTERM, lambda signum, frame: harness.close())
    try:
        session = (
            harness.resume_session(SESSION) if config["resume"] else harness.start_session(SESSION)
        )
        result = session.run([{"type": "text", "text": text} for text in config["blocks"]])
        record = {"finish_reason": result.finish_reason}
    except Exception as error:
        record = {"error_type": type(error).__name__, "detail": str(error)[-1500:]}
    finally:
        harness.close()
        relay.shutdown()
        relay.server_close()
        share_home()
    (TREE / "ipc/result.json").write_text(json.dumps(record))


if __name__ == "__main__":
    main()
