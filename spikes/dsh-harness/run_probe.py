"""Host controller; imports no DSH code and forwards no host environment."""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import math
import os
import re
import socket
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
IMAGE = "sha256:f09faecdfc827f110dfd901bd9be02c84750f6fe220364d13dfad08e037928fb"


def positive_seconds(value: str) -> float:
    seconds = float(value)
    if not math.isfinite(seconds) or seconds <= 0 or seconds > 600:
        raise argparse.ArgumentTypeError(
            "deadline must be finite, positive and at most 600 seconds"
        )
    return seconds


def evidence_error(case: str, requests: list[dict], executions: list[dict]) -> str | None:
    if not requests:
        return "no model-boundary request observed"
    if any(r["poison_visible"] for r in requests):
        return "ungranted skill discovered"
    if case in ("capability", "poison", "local"):
        admitted = [c["tool"] for c in executions if c["admitted"]]
        if set(admitted) != {"lookup_price", "lookup_stock"} or not any(
            r["skill_body_seen"] for r in requests
        ):
            return "skill/tool capability evidence incomplete"
    if case in ("denied-tool", "native-text") and (
        executions or len(requests) != 2 or not any(r["denial_seen"] for r in requests)
    ):
        return "forbidden-call rejection evidence incomplete"
    if case == "native-text" and not any(r["native_input_visible"] for r in requests):
        return "native-shaped task was not observed as model input data"
    if case == "local" and any(
        r.get("provider_status") != 200 or not r.get("provider_usage") for r in requests
    ):
        return "local provider response or usage evidence incomplete"
    return None


def image_id(value: str) -> str:
    if re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None:
        raise argparse.ArgumentTypeError("image must be a local sha256 content ID")
    return value


def run_manifest(case: str, name: str, deadline: float, image: str = IMAGE) -> dict:
    # Reading trusted template data does not import/execute the candidate SDK.
    import yaml
    from preflight import digest, verify

    template = yaml.safe_load((ROOT / "registry/templates/local-default.yaml").read_text())
    profile = yaml.safe_load((ROOT / "registry/profiles/default.yaml").read_text())
    if (
        template["inner_max_turns"] != 8
        or template["turn_timeout"] != "PT10M"
        or template["heartbeat_timeout"] != "PT30S"
    ):
        raise RuntimeError("blocked: template limits changed; refresh spike derivation")
    manifest = {
        "case": case,
        "run_id": name,
        "session": "probe",
        "activity_attempt": 1,
        **verify(),
        "image": image,
        "template": "local-default@1",
        "profile": profile["name"],
        "task_kind": "disposable quote; no Temporal Activity launched",
        "wall_seconds": deadline,
        "model_request_ceiling": 8,
        "inherited_inner_turns": template["inner_max_turns"],
        "task_outer_turns": min(profile["max_turns"], template["max_turns_cap"]),
        "task_token_ceiling": min(profile["max_tokens"], template["max_tokens_cap"]),
        "probe_output_tokens_per_request": 2048,
        "heartbeat_seconds": 30,
        "cleanup_grace_seconds": 5,
        "observation_seconds": 10,
        "phase02_stop_oracle_pending": True,
        "stop_trigger": "host monotonic subprocess deadline",
        "owned_work": "Docker container " + name,
        "clock": "host time.monotonic",
        "source_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, timeout=5
        ).strip(),
        "sources": {str(p.relative_to(HERE)): digest(p) for p in sorted(HERE.glob("*.py"))},
    }
    return manifest


def command(name: str, run: Path, case: str, image: str = IMAGE) -> list[str]:
    site = HERE / ".venv/lib/python3.11/site-packages"
    if not site.is_dir():
        raise RuntimeError("Run uv sync --project spikes/dsh-harness --locked --python 3.11 first")
    return [
        "docker",
        "run",
        "--rm",
        "--pull",
        "never",
        "--name",
        name,
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--pids-limit",
        "128",
        "--memory",
        "1g",
        "--cpus",
        "2",
        "--tmpfs",
        "/tmp:rw,exec,nosuid,nodev,mode=1777",
        "--tmpfs",
        f"/home/spike:rw,exec,nosuid,nodev,uid={os.getuid()},gid={os.getgid()},mode=700",
        "--mount",
        f"type=bind,src={site},dst=/opt/site,readonly",
        *[
            item
            for filename in (
                "container_driver.py",
                "model_gateway.py",
                "mcp_fixture.py",
                "composition.yaml",
            )
            for item in (
                "--mount",
                f"type=bind,src={HERE / filename},dst=/opt/spike/{filename},readonly",
            )
        ],
        "--mount",
        f"type=bind,src={run},dst=/run",
        "--mount",
        f"type=bind,src={ROOT / 'registry/skills/order-desk'},"
        "dst=/opt/granted-skills/order-desk,readonly",
        "--env",
        "PYTHONPATH=/opt/site",
        "--env",
        "PRAXIS_SPIKE_MODEL_KEY=spike-fixture-only",
        "--workdir",
        "/run/workspace",
        image,
        "python",
        "/opt/spike/container_driver.py",
        case,
    ]


def local_provider() -> tuple[str, str]:
    allowed = {"VLLM_BASE_URL", "VLLM_API_KEY"}
    values = {key: os.environ[key] for key in allowed if key in os.environ}
    path = ROOT / "infra/.env"
    if path.is_file():
        for line in path.read_text().splitlines():
            key, separator, value = line.strip().removeprefix("export ").partition("=")
            if separator and key in allowed and key not in values:
                values[key] = value.strip().strip('"').strip("'")
    url = values.get("VLLM_BASE_URL", "")
    target = urlsplit(url)
    if (
        target.scheme not in ("http", "https")
        or not target.hostname
        or target.username
        or target.password
        or target.query
        or target.fragment
    ):
        raise RuntimeError("configure a local VLLM_BASE_URL before the live probe")
    ranges = [
        ipaddress.ip_network(n)
        for n in (
            "10.0.0.0/8",
            "172.16.0.0/12",
            "192.168.0.0/16",
            "127.0.0.0/8",
            "fc00::/7",
            "::1/128",
        )
    ]
    addresses = {
        item[4][0]
        for item in socket.getaddrinfo(target.hostname, target.port or 80, type=socket.SOCK_STREAM)
    }
    if not addresses or any(
        not any(ipaddress.ip_address(address) in network for network in ranges)
        for address in addresses
    ):
        raise RuntimeError("live probe permits only local/private model addresses")
    return url, values.get("VLLM_API_KEY", "")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "case",
        choices=[
            "startup",
            "catalog",
            "capability",
            "poison",
            "denied-tool",
            "native-text",
            "local",
        ],
    )
    parser.add_argument("--deadline", type=positive_seconds, default=40)
    parser.add_argument("--image", type=image_id, default=IMAGE)
    args = parser.parse_args()
    output = HERE / ".runs"
    output.mkdir(exist_ok=True)
    name = "praxis-dsh-" + uuid.uuid4().hex[:12]
    started = time.monotonic()
    manifest = run_manifest(args.case, name, args.deadline, args.image)
    encoded = json.dumps(manifest, sort_keys=True).encode()
    manifest_hash = hashlib.sha256(encoded).hexdigest()
    (output / (name + "-manifest.json")).write_bytes(encoded + b"\n")
    with tempfile.TemporaryDirectory(prefix="dsh-run-", dir=output) as scratch:
        run = Path(scratch)
        (run / "home").mkdir()
        (run / "workspace").mkdir()
        (run / "ipc").mkdir()
        boundary = None
        if args.case != "startup":
            from model_gateway import Boundary

            upstream, api_key = local_provider() if args.case == "local" else (None, "")
            boundary = Boundary(run / "ipc/model.sock", args.case, upstream, api_key)
            boundary.start()
        record = {"case": args.case, "exit": 1, "manifest_sha256": manifest_hash}
        try:
            result = subprocess.run(
                command(name, run, args.case, args.image),
                capture_output=True,
                text=True,
                timeout=args.deadline,
            )
            record.update(
                {
                    "exit": result.returncode,
                    "seconds": round(time.monotonic() - started, 3),
                    "stdout": result.stdout[-2000:],
                    "stderr": result.stderr[-4000:],
                }
            )
        except subprocess.TimeoutExpired:
            record.update(exit=124, error="controller deadline exceeded")
        except Exception as error:
            record.update(exit=1, error=type(error).__name__)
        finally:
            try:
                cleanup = subprocess.run(
                    ["docker", "rm", "-f", name], capture_output=True, timeout=5
                )
                # Normal completion has already removed --rm containers. For a
                # timeout, forced removal is cleanup, never a passing stop probe.
                record["cleanup_command_exit"] = cleanup.returncode
                inspection = subprocess.run(
                    ["docker", "inspect", "--format", "{{.State.Running}}", name],
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
                record["container_absent"] = inspection.returncode != 0
                if not record["container_absent"]:
                    record.update(exit=1, error="probe container survived cleanup")
            except subprocess.TimeoutExpired:
                record.update(exit=1, error="container cleanup deadline exceeded")
            if boundary is not None:
                boundary.close()
                record["model_requests"] = boundary.requests
                calls = run / "fixture-calls.jsonl"
                record["tool_executions"] = (
                    [json.loads(line) for line in calls.read_text().splitlines()]
                    if calls.exists()
                    else []
                )
                error = evidence_error(args.case, boundary.requests, record["tool_executions"])
                if error:
                    record["exit"] = 1
                    record["error"] = error
        (output / (args.case + "-" + name.removeprefix("praxis-dsh-") + ".json")).write_text(
            json.dumps(record, indent=2) + "\n"
        )
        print(json.dumps(record, indent=2))
        return int(record["exit"] != 0)


if __name__ == "__main__":
    raise SystemExit(main())
