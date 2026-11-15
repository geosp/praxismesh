"""DSH SDK entry point used only inside the recovery probe's owned container."""

from __future__ import annotations

import json
import sys

from container_driver import task_input
from model_gateway import serve_relay


def main():
    from deepseek_harness import DeepSeekHarness

    relay = serve_relay("/run/ipc/model.sock")
    try:
        with DeepSeekHarness(
            dsh_home="/run/home",
            cwd="/run/workspace",
            runtime_cwd="/run/workspace",
            profile="sdk-minimal",
            provider="praxis-local",
            model="spark",
            patches=("/opt/spike/recovery-composition.yaml",),
            initialize_timeout_seconds=25,
            request_timeout_seconds=30,
            shutdown_timeout_seconds=1,
            max_tokens=2048,
        ) as harness:
            session = (
                harness.resume_session("recovery")
                if sys.argv[1] == "resume"
                else harness.start_session("recovery")
            )
            result = session.run(task_input("Execute the controlled recovery fixture sequence."))
            print(
                json.dumps(
                    {"finish_reason": result.finish_reason, "final_response": result.final_response}
                ),
                flush=True,
            )
    finally:
        relay.shutdown()
        relay.server_close()


if __name__ == "__main__":
    main()
