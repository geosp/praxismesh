"""Skills: the template's bundle, mounted read-only in the workspace and listed in
the instructions (RFC Phase 1: configure from the template only)."""

from __future__ import annotations

import shutil
import stat
from pathlib import Path

import yaml

SKILLS_DIR = ".skills"


def mount(bundle: Path, workspace: Path) -> Path:
    target = workspace / SKILLS_DIR / bundle.name
    if target.exists():  # re-mount: make the old copy writable again, then replace it
        for p in [target, *target.rglob("*")]:
            p.chmod(p.stat().st_mode | stat.S_IWUSR)
        shutil.rmtree(target)
    shutil.copytree(bundle, target)
    for p in [target, *target.rglob("*")]:
        p.chmod(p.stat().st_mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
    return target


def index(bundle: Path, mounted: Path, workspace: Path) -> str:
    """A skills section for the instructions: name, description and path."""
    text = (bundle / "SKILL.md").read_text()
    meta: dict[str, str] = {}
    if text.startswith("---"):
        meta = yaml.safe_load(text.split("---", 2)[1]) or {}
    name = meta.get("name", bundle.name)
    description = meta.get("description", "")
    path = (mounted / "SKILL.md").relative_to(workspace)
    return (
        "## Skills\n\nA skill is a set of instructions stored in a SKILL.md file. "
        "Read a skill's file with read_file before using it.\n\n"
        f"- {name}: {description} (file: {path})\n"
    )
