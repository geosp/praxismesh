"""Container-only native SDK entry point for the isolated task Activity."""

from __future__ import annotations

import json
import signal
from pathlib import Path

from accounting_driver import primary_usage
from container_driver import task_input
from model_gateway import serve_relay


def main():
    from deepseek_harness import DeepSeekHarness

    config = json.loads(Path("/opt/spike/task-input.json").read_text())
    relay = serve_relay("/run/ipc/model.sock")
    harness = DeepSeekHarness(
        dsh_home="/run/home",
        cwd="/run/workspace",
        runtime_cwd="/run/workspace",
        profile="sdk-minimal",
        provider="praxis-local",
        model="spark",
        patches=("/opt/spike/task-composition.yaml",),
        initialize_timeout_seconds=25,
        request_timeout_seconds=600,
        shutdown_timeout_seconds=1,
        max_tokens=2048,
    )
    signal.signal(signal.SIGTERM, lambda signum, frame: harness.close())
    try:
        session = (
            harness.resume_session("task") if config["resume"] else harness.start_session("task")
        )
        blocks = task_input(config["instructions"])
        if config.get("operating_instructions") and not config["resume"]:
            # Trusted template prompt, ahead of the untrusted task data block.
            blocks.insert(1, {"type": "text", "text": config["operating_instructions"]})
        result = session.run(blocks)
        record = {
            "finish_reason": result.finish_reason,
            "primary_usage": primary_usage(result.events),
        }
    except Exception as error:
        record = {"error_type": type(error).__name__}
    finally:
        harness.close()
        relay.shutdown()
        relay.server_close()
    Path("/run/candidate-result.json").write_text(json.dumps(record))


if __name__ == "__main__":
    main()
