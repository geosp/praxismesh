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


OUTPUTS = [
    ".claude/agents/sample-agent.md",
    ".github/agents/sample-agent.agent.md",
    ".codex/agents/sample-agent.toml",
]


def snapshot(root: Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(root)): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file() and ".agents" not in p.parts
    }


@pytest.mark.parametrize("output", OUTPUTS)
def test_check_fails_on_stale_file(tmp_path: Path, output: str) -> None:
    root = make_root(tmp_path, {"sample-agent.md": AGENT})
    assert run(root).returncode == 0
    generated = root / output
    generated.write_text(generated.read_text() + "# edited by hand\n")
    result = run(root, "--check")
    assert result.returncode == 1
    assert f"stale: {output}" in result.stdout


@pytest.mark.parametrize("output", OUTPUTS)
def test_check_fails_on_orphan_and_sync_deletes_it(tmp_path: Path, output: str) -> None:
    root = make_root(tmp_path, {"sample-agent.md": AGENT})
    assert run(root).returncode == 0
    (root / ".agents" / "agents" / "sample-agent.md").unlink()
    result = run(root, "--check")
    assert result.returncode == 1
    assert f"orphan: {output}" in result.stdout
    assert run(root).returncode == 0
    assert not (root / output).exists()


@pytest.mark.parametrize("args", [(), ("--check",)])
@pytest.mark.parametrize("output", OUTPUTS)
def test_refuses_to_overwrite_hand_written_file(
    tmp_path: Path, output: str, args: tuple[str, ...]
) -> None:
    root = make_root(tmp_path, {"sample-agent.md": AGENT})
    target = root / output
    target.parent.mkdir(parents=True)
    target.write_text("hand written, no marker\n")
    result = run(root, *args)
    assert result.returncode == 2
    assert "refusing to overwrite" in result.stderr
    assert target.read_text() == "hand written, no marker\n"


def test_check_writes_and_deletes_nothing(tmp_path: Path) -> None:
    other = AGENT.replace("name: sample-agent", "name: other-agent")
    root = make_root(tmp_path, {"sample-agent.md": AGENT, "other-agent.md": other})
    assert run(root).returncode == 0
    stale = root / ".claude" / "agents" / "sample-agent.md"
    stale.write_text(stale.read_text() + "stale\n")
    (root / ".agents" / "agents" / "other-agent.md").unlink()
    (root / ".codex" / "agents" / "sample-agent.toml").unlink()
    before = snapshot(root)
    result = run(root, "--check")
    assert result.returncode == 1
    assert snapshot(root) == before


def test_marker_after_long_front_matter_is_recognised(tmp_path: Path) -> None:
    # In Markdown the marker follows the front matter, so a long description must
    # not hide it (it used to be looked for only in the first 2000 characters).
    long_agent = AGENT.replace(
        "description: A sample agent used in tests.",
        "description: " + "A very long description. " * 200,
    )
    root = make_root(tmp_path, {"sample-agent.md": long_agent})
    assert run(root).returncode == 0
    generated = root / OUTPUTS[0]
    assert generated.read_text().index(sync_agents.MARKER) > 2000
    assert run(root).returncode == 0
    (root / ".agents" / "agents" / "sample-agent.md").unlink()
    assert f"orphan: {OUTPUTS[0]}" in run(root, "--check").stdout


def test_interrupted_write_keeps_old_file_and_leaves_no_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "agents" / "x.md"
    target.parent.mkdir()
    target.write_text("old\n")

    def killed(*_: object) -> None:
        raise OSError("killed")

    monkeypatch.setattr("sync_agents.os.replace", killed)
    with pytest.raises(OSError, match="killed"):
        sync_agents.write_atomic(target, "new\n")
    assert target.read_text() == "old\n"
    assert [p.name for p in target.parent.iterdir()] == ["x.md"]


def test_write_atomic_creates_and_replaces(tmp_path: Path) -> None:
    target = tmp_path / "new" / "x.md"
    sync_agents.write_atomic(target, "one\n")
    sync_agents.write_atomic(target, "two\n")
    assert target.read_text() == "two\n"
    assert [p.name for p in target.parent.iterdir()] == ["x.md"]


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
        ("No front matter here.\n", "missing YAML frontmatter"),
        ("---\n- a\n- list\n---\nBody.\n", "frontmatter must be a mapping"),
        (AGENT.replace("claude:\n  tools: Read, Grep", "claude: [Read]"), "mapping or false"),
        (AGENT.replace("claude:\n", "claude:\n  name: other\n"), "override a shared field"),
        (
            AGENT.replace("  sandbox_mode: read-only", "  developer_instructions: x"),
            "override a generated field",
        ),
        (AGENT + "\nA body with ''' inside.\n", "cannot go in a TOML literal string"),
        (AGENT.replace("  sandbox_mode: read-only", "  sandbox_mode: null"), "unsupported value"),
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
