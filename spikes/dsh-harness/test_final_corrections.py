"""Targeted regressions for the second full implementation review."""

import hashlib
import json
import subprocess

import pytest
import run_probe


class BoundaryFixture:
    def __init__(self):
        self.requests = []

    def close(self):
        pass

    def owned_work_alive(self):
        return False


@pytest.mark.parametrize("payload", [b'{"tool":', b"\xff"])
def test_bad_evidence_cannot_bypass_cleanup_or_failed_result(tmp_path, payload):
    run = tmp_path / "state"
    run.mkdir()
    (run / "fixture-calls.jsonl").write_bytes(payload)
    commands = []

    def runner(args, **kwargs):
        commands.append(args)
        return subprocess.CompletedProcess(args, 0, "", "")

    result_path = tmp_path / "result.json"
    record = {"case": "catalog", "exit": 124}
    run_probe.finish_run(
        record,
        "praxis-dsh-fixture",
        run,
        BoundaryFixture(),
        result_path,
        trigger=0,
        runner=runner,
        clock=lambda: 0,
        sleep=lambda _: None,
        window=0,
    )
    assert any("rm" in cmd for cmd in commands)
    assert any("ls" in cmd for cmd in commands)
    saved = json.loads(result_path.read_text())
    assert saved["exit"] != 0
    assert saved["evidence_error_type"] in ("JSONDecodeError", "UnicodeDecodeError")
    assert saved["observations"] > 0


def bundle(tmp_path):
    source = tmp_path / "source"
    skill = tmp_path / "skill"
    source.mkdir()
    skill.mkdir()
    for name in (
        "container_driver.py",
        "model_gateway.py",
        "mcp_fixture.py",
        "composition.yaml",
        "artifacts.json",
        "uv.lock",
    ):
        (source / name).write_text("original\n")
    (skill / "SKILL.md").write_text("granted original skill\n")
    return source, skill


@pytest.mark.parametrize("target", ["container_driver.py", "composition.yaml", "SKILL.md"])
def test_changed_runtime_input_is_rejected_during_staging(tmp_path, target):
    source, skill = bundle(tmp_path)
    expected = run_probe.runtime_identity(source, skill)
    (skill / target if target == "SKILL.md" else source / target).write_text("changed\n")
    with pytest.raises(RuntimeError, match="input"):
        run_probe.stage_inputs(tmp_path / "snapshot", expected, source=source, skill=skill)


def test_mounts_use_snapshot_after_originals_change(tmp_path):
    source, skill = bundle(tmp_path)
    expected = run_probe.runtime_identity(source, skill)
    snapshot = tmp_path / "snapshot"
    run_probe.stage_inputs(snapshot, expected, source=source, skill=skill)
    (source / "composition.yaml").write_text("later change\n")
    (skill / "SKILL.md").write_text("later skill change\n")
    args = run_probe.command("praxis-dsh-fixture", snapshot / "state", "catalog")
    assert (snapshot / "code/composition.yaml").read_text() == "original\n"
    assert (snapshot / "skill/SKILL.md").read_text() == "granted original skill\n"
    assert any(f"src={snapshot / 'code/composition.yaml'}" in value for value in args)
    assert any(f"src={snapshot / 'skill'}" in value for value in args)
    assert all(f"src={run_probe.HERE}/" not in value for value in args)


def test_shared_trigger_detects_gateway_plus_removal_exceeding_grace():
    now = [2.0]  # Gateway already consumed two seconds after trigger zero.

    def runner(args, **kwargs):
        if "rm" in args:
            now[0] += 4
        return subprocess.CompletedProcess(args, 0, "", "")

    result = run_probe.cleanup_container(
        "praxis-dsh-fixture",
        trigger=0,
        runner=runner,
        clock=lambda: now[0],
        sleep=lambda _: None,
        window=0,
    )
    assert result["container_absent"] is True
    assert result["cleanup_ok"] is False
    assert result["grace_met"] is False


def test_manifest_digest_identifies_exact_persisted_bytes(tmp_path):
    path = tmp_path / "manifest.json"
    digest = run_probe.save_manifest(path, {"run": "fixture"})
    assert digest == hashlib.sha256(path.read_bytes()).hexdigest()
    assert path.read_bytes().endswith(b"\n")
