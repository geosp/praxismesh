"""Tests for `.agents/sync_agents.py`, the per-harness agent generator."""

from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
import sync_agents
import yaml

SCRIPT = Path(__file__).resolve().parent.parent / ".agents" / "sync_agents.py"

AGENT = """\
---
name: sample-agent
description: A sample agent used in tests.
claude:
  tools: Read, Grep
copilot:
  tools: [read]
codex:
  sandbox_mode: read-only
---

Do the sample task. Quote "this" and keep a backslash \\ intact.
"""


def make_root(tmp_path: Path, files: dict[str, str]) -> Path:
    root = tmp_path / "repo"
    (root / ".agents" / "agents").mkdir(parents=True)
    for name, text in files.items():
        (root / ".agents" / "agents" / name).write_text(text, encoding="utf-8")
    return root


def run(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def front_matter(text: str) -> dict[str, object]:
    loaded = yaml.safe_load(text.split("---")[1])
    assert isinstance(loaded, dict)
    return loaded


def test_generates_all_three_formats(tmp_path: Path) -> None:
    root = make_root(tmp_path, {"sample-agent.md": AGENT})
    result = run(root)
    assert result.returncode == 0, result.stderr

    claude = (root / ".claude" / "agents" / "sample-agent.md").read_text()
    copilot = (root / ".github" / "agents" / "sample-agent.agent.md").read_text()
    codex = (root / ".codex" / "agents" / "sample-agent.toml").read_bytes()

    assert front_matter(claude)["tools"] == "Read, Grep"
    assert front_matter(copilot)["tools"] == ["read"]
    assert sync_agents.MARKER in claude and sync_agents.MARKER in copilot

    parsed = tomllib.loads(codex.decode())
    assert parsed["name"] == "sample-agent"
    assert parsed["sandbox_mode"] == "read-only"
    assert 'Quote "this"' in parsed["developer_instructions"]
    assert "backslash \\ intact" in parsed["developer_instructions"]


def test_check_passes_when_in_sync(tmp_path: Path) -> None:
    root = make_root(tmp_path, {"sample-agent.md": AGENT})
    assert run(root).returncode == 0
    result = run(root, "--check")
    assert result.returncode == 0
    assert "up to date" in result.stdout


def test_check_fails_on_stale_file(tmp_path: Path) -> None:
    root = make_root(tmp_path, {"sample-agent.md": AGENT})
    assert run(root).returncode == 0
    generated = root / ".claude" / "agents" / "sample-agent.md"
    generated.write_text(generated.read_text() + "edited by hand\n")
    result = run(root, "--check")
    assert result.returncode == 1
    assert "stale: .claude/agents/sample-agent.md" in result.stdout


def test_check_fails_on_orphan_and_sync_deletes_it(tmp_path: Path) -> None:
    root = make_root(tmp_path, {"sample-agent.md": AGENT})
    assert run(root).returncode == 0
    (root / ".agents" / "agents" / "sample-agent.md").unlink()
    result = run(root, "--check")
    assert result.returncode == 1
    assert "orphan:" in result.stdout
    assert run(root).returncode == 0
    assert not (root / ".claude" / "agents" / "sample-agent.md").exists()


def test_refuses_to_overwrite_hand_written_file(tmp_path: Path) -> None:
    root = make_root(tmp_path, {"sample-agent.md": AGENT})
    target = root / ".claude" / "agents" / "sample-agent.md"
    target.parent.mkdir(parents=True)
    target.write_text("hand written, no marker\n")
    result = run(root)
    assert result.returncode == 2
    assert "refusing to overwrite" in result.stderr
    assert target.read_text() == "hand written, no marker\n"


def test_harness_block_false_skips_that_harness(tmp_path: Path) -> None:
    agent = AGENT.replace("codex:\n  sandbox_mode: read-only\n", "codex: false\n")
    root = make_root(tmp_path, {"sample-agent.md": agent})
    assert run(root).returncode == 0
    assert not (root / ".codex" / "agents" / "sample-agent.toml").exists()
    assert (root / ".claude" / "agents" / "sample-agent.md").exists()


@pytest.mark.parametrize(
    ("text", "message"),
    [
        (AGENT.replace("name: sample-agent", "name: Sample_Agent"), "kebab-case"),
        (AGENT.replace("name: sample-agent", "name: other-agent"), "must match file name"),
        (AGENT.replace("description: A sample agent used in tests.\n", ""), "description"),
        (AGENT.replace("claude:", "tools: Read\nclaude:"), "unknown top-level keys"),
        (AGENT.split("\n---\n")[0] + "\n---\n\n", "body is empty"),
    ],
)
def test_rejects_invalid_definitions(tmp_path: Path, text: str, message: str) -> None:
    root = make_root(tmp_path, {"sample-agent.md": text})
    result = run(root)
    assert result.returncode == 2
    assert message in result.stderr


def test_readme_is_ignored(tmp_path: Path) -> None:
    root = make_root(tmp_path, {"README.md": "# Agents\n"})
    result = run(root, "--check")
    assert result.returncode == 0
    assert "0 generated agent file(s)" in result.stdout
