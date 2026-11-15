"""Host authority invariants; live DSH recovery is a separate Docker probe."""

import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from recovery_store import Authority, Superseded, capture_pair, restore_pair


def test_attempt_ownership_fences_every_publication(tmp_path):
    authority = Authority(tmp_path / "authority.db")
    old = authority.claim()
    digest = authority.checkpoint(old, b"acknowledged")
    new = authority.claim()
    for operation in (
        lambda: authority.checkpoint(old, b"stale"),
        lambda: authority.publish(old, {"stale": True}),
        lambda: authority.effect(old, "uncommitted"),
    ):
        with pytest.raises(Superseded):
            operation()
    assert authority.restore() == (digest, b"acknowledged")
    assert authority.counts() == {"business_effects": 0, "admitted_entries": 0, "denied_entries": 1}
    authority.publish(new, {"current": True})


def test_effect_retry_is_atomic_across_independent_connections(tmp_path):
    authority = Authority(tmp_path / "authority.db")
    attempt = authority.claim()
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: authority.effect(attempt, "stable-operation"), range(20)))
    assert all(result["committed"] for result in results)
    assert authority.counts() == {
        "business_effects": 1,
        "admitted_entries": 20,
        "denied_entries": 0,
    }


def test_restore_uses_pair_only_and_refuses_overlay(tmp_path):
    state = tmp_path / "old"
    (state / "home/sessions").mkdir(parents=True)
    (state / "workspace").mkdir()
    (state / "home/sessions/log.jsonl").write_text('"marker"\n')
    (state / "workspace/recovery-note.txt").write_text("marker")
    (state / "home/credential").write_text("excluded")
    payload = capture_pair(state, "marker")
    fresh = tmp_path / "new"
    restore_pair(payload, fresh)
    assert (fresh / "workspace/recovery-note.txt").read_text() == "marker"
    assert not (fresh / "home/credential").exists()
    with pytest.raises(FileExistsError):
        restore_pair(payload, fresh)


@pytest.mark.parametrize(
    "name", ["../escape", "/tmp/escape", "home/config", "workspace/../../escape"]
)
def test_restore_rejects_escape_before_creating_destination(tmp_path, name):
    with pytest.raises(ValueError):
        restore_pair(json.dumps({name: "00"}).encode(), tmp_path / "new")
    assert not (tmp_path / "new").exists()


def test_checkpoint_refuses_symlink_or_missing_marker(tmp_path):
    (tmp_path / "home/sessions").mkdir(parents=True)
    (tmp_path / "workspace").mkdir()
    (tmp_path / "home/sessions/log").write_text("different")
    (tmp_path / "workspace/recovery-note.txt").write_text("marker")
    with pytest.raises(ValueError, match="conversation marker"):
        capture_pair(tmp_path, "marker")
    (tmp_path / "home/sessions/link").symlink_to(tmp_path / "workspace/recovery-note.txt")
    with pytest.raises(ValueError, match="nonregular"):
        capture_pair(tmp_path, "marker")


def test_cleanup_continues_after_initial_removal_and_gateway_errors(monkeypatch):
    import run_recovery

    events = []

    class Resource:
        def __init__(self, name):
            self.name = name

        def close(self):
            events.append(self.name)
            if self.name == "gateway":
                raise RuntimeError("injected close failure")

        def owned_work_alive(self):
            return self.name == "gateway"

    def fail_removal(*args, **kwargs):
        raise OSError("injected daemon error")

    def observe(*args, **kwargs):
        events.append("observe")
        assert not kwargs["owned_work_absent"]()
        return {"cleanup_ok": False, "container_absent": True}

    monkeypatch.setattr(run_recovery, "docker", fail_removal)
    monkeypatch.setattr(run_recovery, "cleanup_container", observe)
    result = run_recovery.stop_owned_attempt(
        "owned", Resource("gateway"), Resource("executor"), None, None
    )
    assert events == ["gateway", "executor", "observe"]
    assert not result["cleanup_ok"]
    assert result["cleanup_errors"] == ["OSError", "RuntimeError"]
