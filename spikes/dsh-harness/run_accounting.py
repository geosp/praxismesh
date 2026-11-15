"""R6 exhaustion/retry/compaction probes through the native SDK/runtime."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import time
import uuid

from preflight import environment_digest
from run_probe import HERE, IMAGE, image_id, run_manifest, save_manifest, stage_inputs
from run_recovery import recovery_command, stop_owned_attempt, wait_barrier


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("case", choices=("exhaustion", "retry", "auxiliary", "tools"))
    parser.add_argument("--image", type=image_id, default=IMAGE)
    args = parser.parse_args()
    name = "praxis-dsh-r6-" + uuid.uuid4().hex[:12]
    manifest = run_manifest(args.case, name, 60, args.image)
    composition = (HERE / "recovery-composition.yaml").read_text()
    if args.case == "retry":
        composition = composition.replace("maxRetries: 0", "maxRetries: 1")
    if args.case == "auxiliary":
        composition = composition.replace(
            "- id: compaction-basic\n  disabled: true",
            "- id: compaction-basic\n  config:\n    auto: false\n    headroomTokens: 1024\n"
            "    maxTokens: 128\n    retainTokens: 1\n    compactionRetries: 0\n",
        )
    encoded = composition.encode()
    manifest.update(
        session="controls",
        case=args.case,
        task_kind="native SDK deterministic accounting fixture",
        composition_sha256=hashlib.sha256(encoded).hexdigest(),
        token_budget_override=1000 if args.case == "tools" else 10,
        setup_budget=1000 if args.case == "auxiliary" else None,
        stop_trigger="first denied ingress after budget exhaustion; watchdog at 60 seconds",
        expected_provider_dispatches=6
        if args.case == "tools"
        else 2
        if args.case == "retry"
        else 1,
        separately_counted_setup_dispatches=3 if args.case == "auxiliary" else 0,
        expected_usage={
            "input": 42 if args.case == "tools" else 4 if args.case == "auxiliary" else 7,
            "output": 18 if args.case == "tools" else 6 if args.case == "auxiliary" else 3,
        },
        auxiliary_inventory={
            "compaction": "one explicit native /compact; same budget gateway"
            if args.case == "auxiliary"
            else "disabled",
            "retries": "one maximum" if args.case == "retry" else "disabled",
            "other_producers": "disabled as in recovery composition",
        },
    )
    output = HERE / ".runs"
    output.mkdir(exist_ok=True)
    manifest_hash = save_manifest(output / (name + "-manifest.json"), manifest)
    scratch = output / name
    scratch.mkdir()
    record = {"case": args.case, "manifest_sha256": manifest_hash, "exit": 1}
    gateway = executor = provider = process = log = None
    started = False
    stop_trigger = None
    try:
        stage_inputs(scratch, manifest)
        (scratch / "code/accounting-composition.yaml").write_bytes(encoded)
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
        store = sys.modules["recovery_store"]
        boundary = sys.modules["accounting_boundary"]
        state = scratch / "state"
        for folder in ("home", "workspace", "ipc"):
            (state / folder).mkdir(parents=True)
        authority = store.Authority(scratch / "authority.sqlite")
        executor = sys.modules["recovery_boundary"].ToolExecutor(
            state, authority, authority.claim(), "accounting-note"
        )
        provider = boundary.FixtureProvider(args.case)
        gateway = boundary.AccountingBoundary(
            state / "ipc/model.sock",
            name,
            provider,
            1000 if args.case in ("auxiliary", "tools") else 10,
        )
        provider.start()
        executor.start()
        gateway.start()
        started = True
        log = (scratch / "candidate.log").open("w+")
        command = recovery_command(name, state, "start", args.image)
        command[-2:] = ["/opt/spike/accounting_driver.py", args.case]
        process = subprocess.Popen(command, stdout=log, stderr=log)
        deadline = time.monotonic() + 60
        if args.case == "auxiliary":
            while not (state / "setup-ready").exists():
                if process.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError("native setup boundary not reached")
                time.sleep(0.02)
            if len(provider.dispatches) != 3 or gateway.ledger.totals()["physical_dispatches"] != 3:
                raise RuntimeError("unexpected setup provider work")
            gateway.begin_auxiliary(name)
            (state / "begin-auxiliary").write_text("controller acknowledged setup")
        if args.case == "tools":
            process.wait(timeout=40)
        else:
            wait_barrier(gateway.denied, process, deadline)
        trigger = time.monotonic()
        stop_trigger = trigger
        # Let the refused request settle naturally; forced removal is cleanup,
        # never evidence that the native turn stopped on its own.
        try:
            process.wait(timeout=5)
            record["native_stopped_after_denial"] = True
        except subprocess.TimeoutExpired:
            record["native_stopped_after_denial"] = False
        record["denial_to_return_seconds"] = round(time.monotonic() - trigger, 3)
        record.update(
            ledger=gateway.ledger.records,
            totals=gateway.ledger.totals(),
            setup_ledger=gateway.setup_ledger.records if gateway.setup_ledger else [],
            provider_dispatches=provider.dispatches,
            tool_entries=executor.entries,
        )
        candidate = state / "candidate-accounting.json"
        record["candidate"] = json.loads(candidate.read_text()) if candidate.exists() else None
        compact = state / "compaction-result.json"
        record["compaction"] = json.loads(compact.read_text()) if compact.exists() else None
        totals = record["totals"]
        measured = [d for d in provider.dispatches if d["stage"] != "setup"]
        expected = manifest["expected_usage"]
        if (
            totals["physical_dispatches"] != manifest["expected_provider_dispatches"]
            or len(measured) != totals["physical_dispatches"]
            or totals["unknown_usage"]
            or totals["input_tokens"] != expected["input"]
            or totals["output_tokens"] != expected["output"]
        ):
            raise RuntimeError("independent provider/ledger usage mismatch")
        if not record["native_stopped_after_denial"]:
            raise RuntimeError("native turn did not stop after admission denial")
        if args.case == "tools":
            counts = {
                "admitted": sum(e["admitted"] for e in executor.entries),
                "success": sum(e.get("outcome") == "success" for e in executor.entries),
                "failure": sum(e.get("outcome") == "FileNotFoundError" for e in executor.entries),
                "policy_denial": sum(r["denial_seen"] for r in gateway.requests),
            }
            record["tool_counts"] = counts
            if counts != {"admitted": 4, "success": 3, "failure": 1, "policy_denial": 1}:
                raise RuntimeError("tool success/failure/denial observations do not reconcile")
        if record["candidate"] is None:
            raise RuntimeError("candidate accounting record missing")
        primary = record["candidate"]["primary_usage"]
        if any(
            type(item[key]) is not int or item[key] < 0
            for item in primary
            for key in ("input_tokens", "output_tokens")
        ):
            raise RuntimeError("invalid candidate usage")
        if len({item["sequence"] for item in primary}) != len(primary):
            raise RuntimeError("ambiguous duplicated candidate usage event")
        provider_in = sum(d["input_tokens"] for d in provider.dispatches)
        provider_out = sum(d["output_tokens"] for d in provider.dispatches)
        if (
            sum(item["input_tokens"] for item in primary) != provider_in
            or sum(item["output_tokens"] for item in primary) != provider_out
        ):
            raise RuntimeError("candidate/provider accounting mismatch")
        if args.case == "auxiliary" and (
            not record["compaction"] or record["compaction"]["finish_reason"] != "completed"
        ):
            raise RuntimeError("native compaction did not complete")
        record["candidate_usage_reconciled"] = True
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
            record["provider_stopped"] = not provider.owned_work_alive()
        if not record.get("cleanup", {}).get("cleanup_ok") or not record.get("provider_stopped"):
            record["exit"] = 1
        (output / (name + "-result.json")).write_text(json.dumps(record, indent=2) + "\n")
        print(json.dumps(record, indent=2))
        # Keep diagnostic records until accounting reconciliation is complete.
    return int(record["exit"] != 0)


if __name__ == "__main__":
    raise SystemExit(main())
