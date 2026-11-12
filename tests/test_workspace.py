"""Deterministic workspace snapshots and the read-only skills mount."""

from __future__ import annotations

from pathlib import Path

import pytest

from harness_activity import skills, workspace
from registry.loader import REGISTRY_ROOT


def make(root: Path) -> None:
    (root / "src").mkdir(parents=True)
    (root / "src" / "a.py").write_text("print(1)\n")
    (root / "notes.md").write_text("hello\n")


def test_pack_is_deterministic_and_round_trips(tmp_path: Path) -> None:
    make(tmp_path / "one")
    make(tmp_path / "two")
    assert workspace.pack(tmp_path / "one") == workspace.pack(tmp_path / "two")
    workspace.unpack(workspace.pack(tmp_path / "one"), tmp_path / "out")
    assert (tmp_path / "out" / "src" / "a.py").read_text() == "print(1)\n"


def test_skills_are_excluded_and_read_only(tmp_path: Path) -> None:
    make(tmp_path)
    before = workspace.pack(tmp_path)
    mounted = skills.mount(REGISTRY_ROOT / "skills" / "order-desk", tmp_path)
    assert workspace.pack(tmp_path) == before
    with pytest.raises(PermissionError):
        (mounted / "SKILL.md").write_text("changed")
    text = skills.index(REGISTRY_ROOT / "skills" / "order-desk", mounted, tmp_path)
    assert "order-desk" in text and ".skills/order-desk/SKILL.md" in text


def test_symlinks_are_not_archived(tmp_path: Path) -> None:
    make(tmp_path)
    (tmp_path / "escape").symlink_to("/etc/passwd")
    workspace.unpack(workspace.pack(tmp_path), tmp_path / "out")
    assert not (tmp_path / "out" / "escape").exists()


def test_skills_can_be_mounted_again(tmp_path: Path) -> None:
    bundle = REGISTRY_ROOT / "skills" / "order-desk"
    skills.mount(bundle, tmp_path)
    mounted = skills.mount(bundle, tmp_path)
    assert (mounted / "SKILL.md").is_file()
