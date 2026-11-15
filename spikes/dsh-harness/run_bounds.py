"""Host R5 wall/step/cancellation probes; run with the root trusted uv project.

Cancellation uses Temporal's ActivityEnvironment, not a deployed Temporal server.
Only the real SDK Activity context launches and cancels that candidate invocation.
The DSH Python SDK remains confined to Docker.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.metadata
import importlib.util
import json
import shutil
import subprocess
import sys
import time
import uuid

from preflight import environment_digest
from run_probe import HERE, IMAGE, ROOT, image_id, run_manifest, save_manifest, stage_inputs
from run_recovery import recovery_command, stop_owned_attempt, wait_barrier


def absent(name: str) -> bool:
    try:
        result = subprocess.run(
            [
                "docker",
                "container",
                "ls",
                "--all",
                "--filter",
                f"name=^/{name}$",
                "--format",
                "{{.ID}}",
            ],
            capture_output=True,
            text=True,
            timeout=0.5,
        )
        return result.returncode == 0 and not result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "case", choices=("stall-model", "stall-tool", "cancel-model", "cancel-tool", "step-limit")
    )
    parser.add_argument("--image", type=image_id, default=IMAGE)
    args = parser.parse_args()
    name = "praxis-dsh-r5-" + uuid.uuid4().hex[:12]
    manifest = run_manifest(args.case, name, 40, args.image)
    composition = (HERE / "recovery-composition.yaml").read_text()
    if args.case.endswith("tool"):
        composition = composition.replace(
            "        cwd: /run/workspace\n",
            "        env:\n          PRAXIS_SPIKE_STALL_CHILD: '1'\n        cwd: /run/workspace\n",
        )
    encoded = composition.encode()
    manifest.update(
        session="controls",
        task_kind="isolated native runtime stop fixture",
        composition_sha256=hashlib.sha256(encoded).hexdigest(),
        trusted_controller_lock_sha256=hashlib.sha256((ROOT / "uv.lock").read_bytes()).hexdigest(),
        temporalio_version=importlib.metadata.version("temporalio"),
        temporal_scope="SDK ActivityEnvironment for cancellation; no deployed worker/server",
        probe_heartbeat_interval_seconds=0.05,
        model_steps_override=2 if args.case == "step-limit" else 8,
        stalled_call_wall_override_seconds=2 if args.case.startswith("stall") else None,
        stalled_clock_anchor="independent provider ingress or tool body entry",
        stop_trigger="third model ingress denied"
        if args.case == "step-limit"
        else "ActivityEnvironment.cancel immediately after independent entry"
        if args.case.startswith("cancel")
        else "two-second monotonic deadline after independent entry",
        owned_work=[
            "container " + name + " and all namespace descendants",
            "host gateway, fixture provider and tool executor threads/sockets",
        ],
    )
    output = HERE / ".runs"
    output.mkdir(exist_ok=True)
    digest = save_manifest(output / (name + "-manifest.json"), manifest)
    scratch = output / name
    scratch.mkdir()
    record = {"case": args.case, "manifest_sha256": digest, "exit": 1}
    gateway = executor = provider = process = log = None
    started = False
    stop_trigger = None
    try:
        stage_inputs(scratch, manifest)
        (scratch / "code/bounded-composition.yaml").write_bytes(encoded)
        shutil.copytree(
            HERE / ".venv/lib/python3.11/site-packages",
            scratch / "environment",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            symlinks=True,
        )
        if environment_digest(scratch / "environment") != manifest["environment_sha256"]:
            raise RuntimeError("blocked: dependency snapshot changed during staging")
        sys.path.insert(0, str(scratch / "code"))
        for module_name in (
            "model_gateway",
            "recovery_store",
            "recovery_boundary",
            "usage_ledger",
            "accounting_boundary",
        ):
            spec = importlib.util.spec_from_file_location(
                module_name, scratch / "code" / (module_name + ".py")
            )
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
        authority = sys.modules["recovery_store"].Authority(scratch / "authority.sqlite")
        state = scratch / "state"
        for folder in ("home", "workspace", "ipc"):
            (state / folder).mkdir(parents=True)
        executor = sys.modules["recovery_boundary"].ToolExecutor(
            state,
            authority,
            authority.claim(),
            "bounded-note",
            hold_effect=args.case.endswith("tool"),
        )
        module = sys.modules["accounting_boundary"]
        provider = module.FixtureProvider(args.case)
        gateway = module.AccountingBoundary(
            state / "ipc/model.sock",
            name,
            provider,
            1000,
            steps=2 if args.case == "step-limit" else 8,
        )
        provider.start()
        executor.start()
        gateway.start()
        started = True
        log = (scratch / "candidate.log").open("w+")
        command = recovery_command(name, state, "start", args.image)
        command[-2:] = ["/opt/spike/bounded_driver.py", "controlled"]
        barrier = (
            gateway.denied
            if args.case == "step-limit"
            else executor.effect_committed
            if args.case.endswith("tool")
            else provider.entered
        )

        def signal_close():
            subprocess.run(
                ["docker", "kill", "--signal=TERM", name],
                check=True,
                capture_output=True,
                timeout=1,
            )

        if args.case.startswith("cancel"):
            from temporalio import activity
            from temporalio.testing import ActivityEnvironment

            async def cancellation_scenario():
                nonlocal process, stop_trigger
                environment = ActivityEnvironment()

                @activity.defn(name="dsh_spike_owned_invocation")
                async def invoke():
                    nonlocal process
                    process = subprocess.Popen(command, stdout=log, stderr=log)
                    try:
                        while process.poll() is None:
                            activity.heartbeat(
                                {"session": "controls", "attempt": activity.info().attempt}
                            )
                            await asyncio.sleep(0.05)
                        raise RuntimeError("candidate ended before Activity cancellation")
                    except asyncio.CancelledError:
                        record["activity_cancellation_delivered"] = activity.is_cancelled()
                        await asyncio.to_thread(signal_close)
                        raise

                task = asyncio.create_task(environment.run(invoke))
                deadline = time.monotonic() + 35
                while not barrier.is_set():
                    if task.done() or time.monotonic() >= deadline:
                        raise RuntimeError("cancel barrier not reached")
                    await asyncio.sleep(0.01)
                stop_trigger = time.monotonic()
                environment.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    record["activity_disposition"] = "cancelled"

            asyncio.run(cancellation_scenario())
        else:
            process = subprocess.Popen(command, stdout=log, stderr=log)
            wait_barrier(barrier, process, time.monotonic() + 35)
            if args.case.startswith("stall"):
                deadline = time.monotonic() + 2
                while time.monotonic() < deadline:
                    time.sleep(min(0.02, deadline - time.monotonic()))
                stop_trigger = deadline
                signal_close()
            else:
                stop_trigger = time.monotonic()
        until = stop_trigger + 5
        graceful = False
        while time.monotonic() < until:
            if process.poll() is not None and absent(name):
                graceful = True
                break
            time.sleep(0.02)
        record.update(
            cooperative_stop=graceful,
            stop_to_absence_seconds=round(time.monotonic() - stop_trigger, 3),
            ledger=gateway.ledger.records,
            provider_dispatches=provider.dispatches,
            tool_entries=executor.entries,
        )
        if not graceful:
            raise RuntimeError("owned runtime failed cooperative five-second stop bound")
        if args.case == "step-limit" and gateway.ledger.totals()["physical_dispatches"] != 2:
            raise RuntimeError("model-step ceiling did not admit exactly two steps")
        if args.case.startswith("cancel") and not record.get("activity_cancellation_delivered"):
            raise RuntimeError("SDK Activity context did not receive cancellation")
        record["exit"] = 0
    except Exception as error:
        record.update(
            exit=1,
            error_type=type(error).__name__,
            error=str(error) if isinstance(error, RuntimeError) else "probe failed",
        )
    finally:
        if started:
            record["cleanup"] = stop_owned_attempt(
                name, gateway, executor, process, log, trigger=stop_trigger
            )
        if provider is not None:
            provider.close()
        if not record.get("cleanup", {}).get("cleanup_ok"):
            record["exit"] = 1
        (output / (name + "-result.json")).write_text(json.dumps(record, indent=2) + "\n")
        print(json.dumps(record, indent=2))
    return int(record["exit"] != 0)


if __name__ == "__main__":
    raise SystemExit(main())
