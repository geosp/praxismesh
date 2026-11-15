"""Host controller; imports no DSH code and forwards no host environment."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import ipaddress
import json
import math
import os
import re
import shutil
import socket
import subprocess
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
IMAGE = "sha256:f09faecdfc827f110dfd901bd9be02c84750f6fe220364d13dfad08e037928fb"
ALLOWED_TOOLS = {"skill", "mcp__sample-shop__lookup_price", "mcp__sample-shop__lookup_stock"}


def runtime_identity(source: Path, skill: Path) -> dict:
    from preflight import digest

    files = sorted(source.glob("*.py")) + [
        source / name for name in ("composition.yaml", "artifacts.json", "uv.lock")
    ]

    def skill_identity(root):
        entries = {}
        for path in sorted(root.rglob("*")):
            if path.is_symlink():
                raise RuntimeError("blocked: runtime input symlink")
            if path.is_file():
                entries[path.relative_to(root).as_posix()] = digest(path)
        return entries

    if any(path.is_symlink() for path in files):
        raise RuntimeError("blocked: runtime input symlink")
    return {
        "runtime_inputs": {p.name: digest(p) for p in files},
        "skill_inputs": skill_identity(skill),
    }


def stage_inputs(
    scratch: Path,
    expected: dict,
    *,
    source: Path = HERE,
    skill: Path = ROOT / "registry/skills/order-desk",
) -> None:
    code = scratch / "code"
    code.mkdir(parents=True)
    for name in expected["runtime_inputs"]:
        shutil.copy2(source / name, code / name, follow_symlinks=False)
    shutil.copytree(skill, scratch / "skill", symlinks=True)
    staged = runtime_identity(code, scratch / "skill")
    if any(staged[key] != expected[key] for key in ("runtime_inputs", "skill_inputs")):
        raise RuntimeError("blocked: runtime input changed during staging")


def save_manifest(path: Path, manifest: dict) -> str:
    encoded = json.dumps(manifest, sort_keys=True).encode() + b"\n"
    path.write_bytes(encoded)
    return hashlib.sha256(encoded).hexdigest()


def snapshot_gateway(code: Path):
    spec = importlib.util.spec_from_file_location("dsh_frozen_gateway", code / "model_gateway.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.Boundary


def auxiliary_inventory() -> dict:
    return {
        name: {"admission": "disabled", "bounds": "not admitted", "accounting": "not admitted"}
        for name in (
            "title_generation",
            "jobs",
            "compaction",
            "image_offload",
            "delegation",
            "mcp_resources",
        )
    } | {
        "internal_timers": {
            "admission": "internal only",
            "bounds": "container wall deadline and observation",
            "accounting": "no model/tool producer; gateway catalog and request ledger",
        },
        "skill_and_mcp": {
            "admission": "three granted tools",
            "bounds": "container wall deadline; MCP call timeout 10s",
            "accounting": (
                "gateway skill-result evidence and fixture body-entry ledger; "
                "full reconciliation Phase 02"
            ),
        },
    }


def cleanup_container(
    name: str,
    *,
    runner=subprocess.run,
    clock=time.monotonic,
    sleep=time.sleep,
    window: float = 10,
    trigger: float | None = None,
    grace: float = 5,
    owned_work_absent=None,
) -> dict:
    started = clock() if trigger is None else trigger
    result = {"container_absent": False, "cleanup_ok": True, "observations": 0}
    try:
        remaining = grace - (clock() - started)
        removal = runner(
            ["docker", "rm", "-f", name],
            capture_output=True,
            text=True,
            timeout=max(0.01, remaining),
        )
        result["cleanup_command_exit"] = removal.returncode
    except (OSError, subprocess.TimeoutExpired):
        result["cleanup_ok"] = False
    while True:
        try:
            # Successful daemon listing, including stopped containers, is the
            # absence oracle. CLI/daemon failures always leave state unknown.
            inspection = runner(
                [
                    "docker",
                    "container",
                    "ls",
                    "--all",
                    "--no-trunc",
                    "--filter",
                    f"name=^/{name}$",
                    "--format",
                    "{{.ID}}",
                ],
                capture_output=True,
                text=True,
                timeout=max(0.01, min(2, window - (clock() - started))),
            )
            absent = inspection.returncode == 0 and not inspection.stdout.strip()
            if owned_work_absent is not None:
                absent = absent and owned_work_absent()
        except (OSError, subprocess.TimeoutExpired):
            absent = False
        result["observations"] += 1
        result["container_absent"] = absent
        if "grace_met" not in result:
            result["grace_met"] = absent and clock() - started <= grace
            if not result["grace_met"]:
                result["cleanup_ok"] = False
        if not absent:
            result["cleanup_ok"] = False
        elapsed = clock() - started
        if elapsed >= window:
            break
        sleep(min(0.5, window - elapsed))
    result["observation_seconds"] = round(clock() - started, 3)
    return result


def finish_run(
    record: dict,
    name: str,
    run: Path,
    boundary,
    result_path: Path,
    *,
    trigger: float,
    runner=subprocess.run,
    clock=time.monotonic,
    sleep=time.sleep,
    window: float = 10,
) -> None:
    # Mandatory teardown is independent of decoding untrusted, possibly partial
    # evidence. Never let evidence failures skip removal or result persistence.
    try:
        if boundary is not None:
            boundary.close()
            record["gateway_stopped"] = not boundary.owned_work_alive()
            if not record["gateway_stopped"]:
                record.update(exit=1, error="host gateway survived cleanup")
    except Exception as error:
        record.update(exit=1, gateway_stopped=False, gateway_error_type=type(error).__name__)
    finally:
        try:
            record.update(
                cleanup_container(
                    name, runner=runner, clock=clock, sleep=sleep, window=window, trigger=trigger
                )
            )
            if not record["cleanup_ok"]:
                record.update(exit=1, error="cleanup unknown, late or surviving work observed")
        except Exception as error:
            record.update(exit=1, cleanup_ok=False, cleanup_error_type=type(error).__name__)
    try:
        if boundary is not None:
            record["model_requests"] = boundary.requests
            calls = run / "fixture-calls.jsonl"
            record["tool_executions"] = (
                [json.loads(line) for line in calls.read_text().splitlines()]
                if calls.exists()
                else []
            )
            error = evidence_error(record["case"], boundary.requests, record["tool_executions"])
            if error:
                record.update(exit=1, error=error)
    except Exception as error:
        record.update(exit=1, evidence_error_type=type(error).__name__)
    finally:
        result_path.write_text(json.dumps(record, indent=2) + "\n")


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
    if any(set(r.get("tools", [])) != ALLOWED_TOOLS or r.get("model") != "spark" for r in requests):
        return "effective tool/model grants changed"
    if any(r["poison_visible"] for r in requests):
        return "ungranted skill discovered"
    if case == "poison" and not any(r["denial_seen"] for r in requests):
        return "introduced plugin operation was not rejected"
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
        "scratch_directory": str(HERE / ".runs" / name),
        "session": "probe",
        "activity_attempt": 1,
        **verify(),
        **runtime_identity(HERE, ROOT / "registry/skills/order-desk"),
        "manifest_hash_policy": "SHA-256 of exact persisted UTF-8 bytes including final newline",
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
        "owned_work": [
            "Docker container " + name,
            "host gateway listener, handlers and provider sockets for " + name,
        ],
        "auxiliary_inventory": auxiliary_inventory(),
        "clock": "host time.monotonic",
        "source_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, timeout=5
        ).strip(),
        "sources": {str(p.relative_to(HERE)): digest(p) for p in sorted(HERE.glob("*.py"))},
    }
    return manifest


def command(name: str, run: Path, case: str, image: str = IMAGE) -> list[str]:
    site = run.parent / "environment"
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
                f"type=bind,src={run.parent / 'code' / filename},"
                f"dst=/opt/spike/{filename},readonly",
            )
        ],
        "--mount",
        f"type=bind,src={run},dst=/run",
        "--mount",
        f"type=bind,src={run.parent / 'skill'},dst=/opt/granted-skills/order-desk,readonly",
        "--env",
        "PYTHONPATH=/opt/site",
        "--env",
        "PYTHONPYCACHEPREFIX=/tmp/bytecode",
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
    manifest_hash = save_manifest(output / (name + "-manifest.json"), manifest)
    scratch = Path(manifest["scratch_directory"])
    scratch.mkdir()  # UUID name; never reuse or overwrite an earlier run.
    try:
        stage_inputs(scratch, manifest)
        shutil.copytree(
            HERE / ".venv/lib/python3.11/site-packages",
            scratch / "environment",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            symlinks=True,
        )
        from preflight import environment_digest

        if environment_digest(scratch / "environment") != manifest["environment_sha256"]:
            raise RuntimeError("blocked: dependency snapshot changed during staging")
        run = scratch / "state"
        run.mkdir()
        (run / "home").mkdir()
        (run / "workspace").mkdir()
        (run / "ipc").mkdir()
        boundary = None
        if args.case != "startup":
            Boundary = snapshot_gateway(scratch / "code")

            upstream, api_key = local_provider() if args.case == "local" else (None, "")
            boundary = Boundary(run / "ipc/model.sock", args.case, upstream, api_key)
            boundary.start()
        record = {"case": args.case, "exit": 1, "manifest_sha256": manifest_hash}
        candidate_started = time.monotonic()
        stop_trigger = None
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
            stop_trigger = candidate_started + args.deadline
            record.update(exit=124, error="controller deadline exceeded")
        except Exception as error:
            record.update(exit=1, error=type(error).__name__)
        finally:
            stop_trigger = time.monotonic() if stop_trigger is None else stop_trigger
            finish_run(
                record,
                name,
                run,
                boundary,
                output / (args.case + "-" + name.removeprefix("praxis-dsh-") + ".json"),
                trigger=stop_trigger,
            )
        print(json.dumps(record, indent=2))
        return int(record["exit"] != 0)
    finally:
        # Preserve unknown/live state for explicit recovery; never erase its
        # ownership record or credentials while owned work may still use it.
        if "record" not in locals() or (
            record.get("cleanup_ok") and record.get("gateway_stopped", True)
        ):
            shutil.rmtree(scratch)


if __name__ == "__main__":
    raise SystemExit(main())
