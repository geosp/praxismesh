"""Container-only SDK runner with a cooperative signal-to-close bridge."""

from __future__ import annotations

import json
import signal

from container_driver import task_input
from model_gateway import serve_relay


def main():
    from deepseek_harness import DeepSeekHarness

    relay = serve_relay("/run/ipc/model.sock")
    harness = DeepSeekHarness(
        dsh_home="/run/home",
        cwd="/run/workspace",
        runtime_cwd="/run/workspace",
        profile="sdk-minimal",
        provider="praxis-local",
        model="spark",
        patches=("/opt/spike/bounded-composition.yaml",),
        initialize_timeout_seconds=25,
        request_timeout_seconds=30,
        shutdown_timeout_seconds=1,
        max_tokens=2048,
    )
    cancelled = False

    def close_on_signal(signum, frame):
        nonlocal cancelled
        cancelled = True
        harness.close()

    signal.signal(signal.SIGTERM, close_on_signal)
    try:
        harness.start()
        try:
            result = harness.run(
                task_input("Execute the bounded control fixture."), session_id="controls"
            )
            record = {"finish_reason": result.finish_reason, "cancelled": cancelled}
        except Exception as error:
            if not cancelled:
                raise
            record = {"cancelled": True, "error_type": type(error).__name__}
        print(json.dumps(record), flush=True)
    finally:
        harness.close()
        relay.shutdown()
        relay.server_close()


if __name__ == "__main__":
    main()
