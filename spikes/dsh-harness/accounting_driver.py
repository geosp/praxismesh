"""Container-only SDK accounting probe; controller owns budget stage changes."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from container_driver import task_input
from model_gateway import serve_relay


def usage_observations(value, path="") -> list[dict]:
    result = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "usage" and isinstance(child, dict):
                # Only numeric accounting fields; never copy content/transcripts.
                result.append(
                    {
                        "path": path + "/usage",
                        "fields": {
                            name: number
                            for name, number in child.items()
                            if type(number) in (int, float)
                        },
                    }
                )
            else:
                result.extend(usage_observations(child, path + "/" + str(key)))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            result.extend(usage_observations(child, path + "/" + str(index)))
    return result


def primary_usage(events: list[dict]) -> list[dict]:
    return [
        {
            "sequence": event["seq"],
            "input_tokens": event["data"]["usage"]["inputTokens"],
            "output_tokens": event["data"]["usage"]["outputTokens"],
        }
        for event in events
        if event.get("type") == "assistant/message" and "usage" in event.get("data", {})
    ]


def main():
    from deepseek_harness import DeepSeekHarness

    relay = serve_relay("/run/ipc/model.sock")
    observed = []
    primary = []
    try:
        with DeepSeekHarness(
            dsh_home="/run/home",
            cwd="/run/workspace",
            runtime_cwd="/run/workspace",
            profile="sdk-minimal",
            provider="praxis-local",
            model="spark",
            patches=("/opt/spike/accounting-composition.yaml",),
            initialize_timeout_seconds=25,
            request_timeout_seconds=30,
            shutdown_timeout_seconds=1,
            max_tokens=2048,
        ) as harness:
            session = harness.start_session("controls")
            if sys.argv[1] == "auxiliary":
                for index in range(3):
                    result = session.run(
                        task_input(f"Fixture history setup {index}. " + "setup detail. " * 500)
                    )
                    observed.extend(usage_observations(result.events))
                    primary.extend(primary_usage(result.events))
                    if result.finish_reason != "completed":
                        raise RuntimeError("setup did not complete")
                Path("/run/setup-ready").write_text("three completed setup turns")
                deadline = time.monotonic() + 20
                while not Path("/run/begin-auxiliary").exists():
                    if time.monotonic() >= deadline:
                        raise TimeoutError("controller did not acknowledge setup boundary")
                    time.sleep(0.02)
                result = session.run("/compact")
                observed.extend(usage_observations(result.events))
                primary.extend(primary_usage(result.events))
                Path("/run/compaction-result.json").write_text(
                    json.dumps(
                        {
                            "finish_reason": result.finish_reason,
                            "usage_observations": usage_observations(result.events),
                        }
                    )
                )
            result = session.run(task_input("Execute the controlled accounting fixture."))
            observed.extend(usage_observations(result.events))
            primary.extend(primary_usage(result.events))
            Path("/run/candidate-accounting.json").write_text(
                json.dumps(
                    {
                        "finish_reason": result.finish_reason,
                        "usage_observations": observed,
                        "primary_usage": primary,
                    }
                )
            )
    finally:
        relay.shutdown()
        relay.server_close()


if __name__ == "__main__":
    main()
