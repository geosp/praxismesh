"""Host-only R4 interruption probe. No candidate SDK is imported on the host."""

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
from pathlib import Path

from preflight import environment_digest
from run_probe import (
    HERE,
    IMAGE,
    cleanup_container,
    command,
    image_id,
    run_manifest,
    save_manifest,
    stage_inputs,
)


def docker(*args, check=True):
    return subprocess.run(["docker", *args], check=check, capture_output=True, timeout=5)


def wait_barrier(event, process, deadline):
    while not event.wait(0.05):
        if process.poll() is not None:
            raise RuntimeError("candidate exited before required interruption barrier")
        if time.monotonic() >= deadline:
            raise TimeoutError("interruption barrier not reached")


def recovery_command(name, state, stage, image):
    args = command(name, state, "startup", image)
    # Replace the Phase 01 file mounts with the complete frozen probe code tree.
    result = []
    index = 0
    while index < len(args):
        if args[index] == "--mount" and "dst=/opt/spike/" in args[index + 1]:
            index += 2
        else:
            result.append(args[index])
            index += 1
    insert = result.index("--workdir")
    result[insert:insert] = [
        "--mount",
        f"type=bind,src={state.parent / 'code'},dst=/opt/spike,readonly",
    ]
    result[-2:] = ["/opt/spike/recovery_driver.py", stage]
    return result


def stop_owned_attempt(name, model, executor, process, log) -> dict:
    trigger = time.monotonic()
    errors = []
    # Killing before releasing the held response is the injected worker loss.
    # Every later cleanup still runs if an earlier one fails.
    for close in (
        lambda: docker("rm", "-f", name, check=False),
        lambda: model.close() if model is not None else None,
        lambda: executor.close() if executor is not None else None,
    ):
        try:
            close()
        except Exception as error:
            errors.append(type(error).__name__)
    try:
        observation = cleanup_container(
            name,
            trigger=trigger,
            owned_work_absent=lambda: all(
                resource is None or not resource.owned_work_alive()
                for resource in (model, executor)
            ),
        )
    except Exception as error:
        errors.append(type(error).__name__)
        observation = {"cleanup_ok": False, "container_absent": False}
    try:
        if process is not None:
            process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        errors.append("DockerClientSurvived")
        process.kill()  # Popen handle for this owned CLI, never a searched/reused PID
        process.wait(timeout=2)
    finally:
        if log is not None:
            log.close()
    if errors:
        observation.update(cleanup_ok=False, cleanup_errors=errors)
    return observation


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", type=image_id, default=IMAGE)
    args = parser.parse_args()
    name = "praxis-dsh-r4-" + uuid.uuid4().hex[:12]
    output = HERE / ".runs"
    output.mkdir(exist_ok=True)
    manifest = run_manifest("recovery", name, 120, args.image)
    composition = (HERE / "recovery-composition.yaml").read_bytes()
    manifest.update(
        session="recovery",
        activity_attempts=[1, 2, 3, 4, 5],
        task_kind="host-controlled interruption fixture; no Temporal Activity launched",
        recovery_composition_sha256=hashlib.sha256(composition).hexdigest(),
        barrier="native pre-model flush, held gateway request, paused candidate cgroup",
        stop_trigger="independent model ingress or committed effect, then injected worker loss",
        expected_sequence=[
            "edit/checkpoint/loss",
            "effect commit/loss",
            "effect retry",
            "superseded publication",
        ],
    )
    manifest_hash = save_manifest(output / (name + "-manifest.json"), manifest)
    scratch = Path(manifest["scratch_directory"])
    scratch.mkdir()
    record = {"case": "recovery", "manifest_sha256": manifest_hash, "exit": 1, "attempts": []}
    active = None
    model = executor = process = log = None
    clean = True
    try:
        stage_inputs(scratch, manifest)
        (scratch / "code/recovery-composition.yaml").write_bytes(composition)
        shutil.copytree(
            HERE / ".venv/lib/python3.11/site-packages",
            scratch / "environment",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            symlinks=True,
        )
        if environment_digest(scratch / "environment") != manifest["environment_sha256"]:
            raise RuntimeError("blocked: dependency snapshot changed during staging")
        # Load only trusted frozen host modules; the native SDK stays container-only.
        sys.path.insert(0, str(scratch / "code"))
        for module_name in ("model_gateway", "recovery_store", "recovery_boundary"):
            spec = importlib.util.spec_from_file_location(
                module_name, scratch / "code" / (module_name + ".py")
            )
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
        store = sys.modules["recovery_store"]
        boundary = sys.modules["recovery_boundary"]
        authority = store.Authority(scratch / "authority.sqlite")
        marker = "checkpoint-marker-" + uuid.uuid4().hex
        checkpoint = None

        def stop_attempt():
            nonlocal active, model, executor, process, log, clean
            observation = stop_owned_attempt(active, model, executor, process, log)
            clean = clean and observation["cleanup_ok"]
            if record["attempts"]:
                record["attempts"][-1]["cleanup"] = observation
            active = model = executor = process = log = None
            if not clean:
                raise RuntimeError("owned attempt cleanup failed")

        for stage in ("checkpoint", "effect-loss", "retry", "stale"):
            state = scratch / "state"
            if state.exists():
                shutil.rmtree(state)
            if checkpoint is None:
                (state / "home").mkdir(parents=True)
                (state / "workspace").mkdir()
            else:
                digest, payload = authority.restore()
                if digest != checkpoint:
                    raise RuntimeError("acknowledged checkpoint changed")
                store.restore_pair(payload, state)
            (state / "ipc").mkdir()
            attempt = authority.claim()
            active = name + f"-a{attempt}"
            model = boundary.RecoveryModel(state / "ipc/model.sock", stage, marker)
            executor = boundary.ToolExecutor(
                state, authority, attempt, marker, hold_effect=stage in ("effect-loss", "stale")
            )
            entry = {
                "attempt": attempt,
                "stage": stage,
                "container": active,
                "restored_only_acknowledged_pair": checkpoint is not None,
            }
            record["attempts"].append(entry)
            model.start()
            executor.start()
            log = (scratch / f"attempt-{attempt}.log").open("w+")
            process = subprocess.Popen(
                recovery_command(
                    active, state, "start" if stage == "checkpoint" else "resume", args.image
                ),
                stdout=log,
                stderr=log,
            )
            deadline = time.monotonic() + 40
            if stage == "checkpoint":
                wait_barrier(model.barrier, process, deadline)
                if not model.conversation_restored:
                    raise RuntimeError("edit result absent from next model request")
                docker("pause", active)
                payload = store.capture_pair(state, marker)
                checkpoint = authority.checkpoint(attempt, payload)
                entry.update(
                    checkpoint_sha256=checkpoint,
                    native_flush_observed=True,
                    workspace_and_conversation_acknowledged=True,
                )
            elif stage in ("effect-loss", "stale"):
                wait_barrier(executor.effect_committed, process, deadline)
                if not model.conversation_restored:
                    raise RuntimeError("clean worker did not restore conversation")
                entry["effect_committed_before_response"] = True
                if stage == "stale":
                    newer = authority.claim()
                    docker("pause", active)
                    stale_payload = store.capture_pair(state, marker)
                    try:
                        authority.checkpoint(attempt, stale_payload)
                    except store.Superseded:
                        entry["stale_checkpoint_refused"] = True
                    else:
                        raise RuntimeError("stale checkpoint accepted")
                    docker("unpause", active)
                    executor.release.set()
                    process.wait(timeout=20)
                    log.flush()
                    lines = (scratch / f"attempt-{attempt}.log").read_text().splitlines()
                    candidate_result = next(
                        json.loads(line)
                        for line in reversed(lines)
                        if line.startswith('{"finish_reason"')
                    )
                    try:
                        authority.publish(attempt, candidate_result)
                    except store.Superseded:
                        entry.update(stale_outcome_refused=True, newer_attempt=newer)
                    else:
                        raise RuntimeError("stale outcome accepted")
                    if not any(e.get("outcome") == "Superseded" for e in executor.entries):
                        raise RuntimeError("stale held tool returned authoritative success")
            else:
                process.wait(timeout=35)
                if process.returncode != 0 or not model.conversation_restored:
                    raise RuntimeError("replacement runtime did not complete recovery fixture")
                if authority.counts() != {
                    "business_effects": 1,
                    "admitted_entries": 2,
                    "denied_entries": 0,
                }:
                    raise RuntimeError("effect retry duplicated or missed execution")
                authority.publish(attempt, {"fixture": "completed"})
                entry["effect_retry_deduplicated"] = True
            entry["model_requests"] = model.requests
            entry["tool_entries"] = executor.entries
            if stage != "checkpoint" and not any(
                e.get("restored_note_matches") is True for e in executor.entries
            ):
                raise RuntimeError("replacement workspace content did not survive")
            stop_attempt()
        record.update(
            exit=0, counts=authority.counts(), cleanup_ok=clean, acknowledged_pair_sha256=checkpoint
        )
        if not clean:
            raise RuntimeError("owned work cleanup failed")
    except Exception as error:
        record.update(
            exit=1,
            error_type=type(error).__name__,
            error=str(error) if isinstance(error, (RuntimeError, TimeoutError)) else "probe failed",
        )
    finally:
        if active is not None:
            try:
                stop_attempt()
            except Exception as error:
                clean = False
                record.update(exit=1, cleanup_error_type=type(error).__name__)
        record["cleanup_ok"] = clean
        (output / (name + "-result.json")).write_text(json.dumps(record, indent=2) + "\n")
        print(json.dumps(record, indent=2))
        # Retain failed runs for diagnosis. Successful evidence is sanitized above.
        if record["exit"] == 0 and clean:
            shutil.rmtree(scratch)
    return int(record["exit"] != 0)


if __name__ == "__main__":
    raise SystemExit(main())
