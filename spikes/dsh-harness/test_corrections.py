"""Review regressions, added before their implementation corrections."""

import contextlib
import json
import subprocess
import threading
import time
from pathlib import Path

import preflight
import pytest
import run_probe
from model_gateway import ALLOWED_TOOLS, Boundary
from test_probe import observation, request


def test_complete_environment_blocks_changed_unlisted_dependency(tmp_path, monkeypatch):
    site = tmp_path / "site"
    site.mkdir()
    dependency = site / "other_imported_module.py"
    dependency.write_text("original = True\n")
    manifest = json.loads((preflight.HERE / "artifacts.json").read_text())
    manifest["installed_sha256"] = {}
    manifest["environment_sha256"] = preflight.environment_digest(site)
    (tmp_path / "artifacts.json").write_text(json.dumps(manifest))
    monkeypatch.setattr(preflight, "HERE", tmp_path)
    dependency.write_text("original = False\n")
    with pytest.raises(RuntimeError, match="environment"):
        preflight.verify(site)


def fake_docker(returncode, stdout="", stderr=""):
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


def test_cleanup_daemon_errors_never_confirm_absence():
    def broken(*args, **kwargs):
        return fake_docker(1, stderr="Cannot connect to Docker daemon")

    result = run_probe.cleanup_container("praxis-dsh-fixture", runner=broken, window=0)
    assert result["container_absent"] is False
    assert result["cleanup_ok"] is False


def test_observer_detects_late_work_through_full_window():
    now = [0.0]

    def runner(args, **kwargs):
        if "rm" in args:
            return fake_docker(0)
        return fake_docker(0, stdout="late-container" if now[0] >= 3 else "")

    result = run_probe.cleanup_container(
        "praxis-dsh-fixture",
        runner=runner,
        clock=lambda: now[0],
        sleep=lambda seconds: now.__setitem__(0, now[0] + seconds),
        window=10,
    )
    assert now[0] >= 10
    assert result["cleanup_ok"] is False
    assert result["observation_seconds"] >= 10


def test_unexpected_tool_catalog_is_rejected():
    unexpected = observation(tools=["ungranted_plugin_tool"], model="spark")
    assert run_probe.evidence_error("catalog", [unexpected], []) is not None


def test_auxiliary_paths_have_enforced_admission_policy():
    import yaml

    policy = run_probe.auxiliary_inventory()
    assert policy
    assert all(
        path["admission"] == "disabled" or (path["bounds"] and path["accounting"])
        for path in policy.values()
    )
    assert policy["title_generation"]["admission"] == "disabled"
    rows = yaml.safe_load((run_probe.HERE / "composition.yaml").read_text())
    disabled = {row.get("id") for row in rows if row.get("disabled") is True}
    assert {
        "session-title",
        "jobs",
        "mcp-resources",
        "compaction-basic",
        "image-offload",
    } <= disabled
    loop = next(row for row in rows if row.get("id") == "agent-loop")
    assert loop["config"]["agents"] == []


def test_gateway_shutdown_joins_stalled_provider_handler(tmp_path):
    import http.server

    entered = threading.Event()
    release = threading.Event()

    class Stalled(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            entered.set()
            release.wait(5)

        def log_message(self, *args):
            pass

    provider = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Stalled)
    thread = threading.Thread(target=provider.serve_forever, daemon=True)
    thread.start()
    boundary = Boundary(
        tmp_path / "model.sock", "local", f"http://127.0.0.1:{provider.server_port}"
    )
    boundary.start()

    def call():
        with contextlib.suppress(OSError, TimeoutError):
            request(
                boundary,
                "POST",
                "/v1/chat/completions",
                json.dumps(
                    {
                        "model": "spark",
                        "messages": [],
                        "tools": [{"function": {"name": name}} for name in ALLOWED_TOOLS],
                    }
                ).encode(),
            )

    client = threading.Thread(target=call, daemon=True)
    client.start()
    try:
        assert entered.wait(2)
        started = time.monotonic()
        boundary.close()
        assert time.monotonic() - started < 2
        assert not boundary.owned_work_alive()
        client.join(1)
        assert not client.is_alive()
    finally:
        release.set()
        provider.shutdown()
        provider.server_close()


def test_manifest_identifies_exact_nonoverlapping_scratch_paths():
    one = run_probe.run_manifest("catalog", "praxis-dsh-one", 40)
    two = run_probe.run_manifest("catalog", "praxis-dsh-two", 40)
    assert one["scratch_directory"] != two["scratch_directory"]
    assert Path(one["scratch_directory"]).name == "praxis-dsh-one"
