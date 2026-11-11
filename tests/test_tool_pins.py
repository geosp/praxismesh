"""Checks that tool versions pinned in more than one place agree."""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def locked_version(lockfile: Path, package: str) -> str:
    data = tomllib.loads(lockfile.read_text(encoding="utf-8"))
    versions = {str(p["version"]) for p in data["package"] if p["name"] == package}
    assert len(versions) == 1, f"{lockfile.name}: expected one {package}, got {versions}"
    return versions.pop()


def test_sync_script_pyyaml_matches_project_lock() -> None:
    # CI runs the sync script from its own lockfile; the tests import it with the
    # project's. Both must resolve the same PyYAML, or `--check` and the tests could
    # disagree. After a bump: uv lock --script .agents/sync_agents.py --upgrade-package pyyaml
    script = locked_version(ROOT / ".agents" / "sync_agents.py.lock", "pyyaml")
    project = locked_version(ROOT / "uv.lock", "pyyaml")
    assert script == project


def test_openspec_version_is_the_same_everywhere() -> None:
    # A Dependabot bump of .github/tools must also update the README install line and
    # regenerate the openspec-* skills (`openspec update --force`).
    tools = ROOT / ".github" / "tools"
    pinned = json.loads((tools / "package.json").read_text(encoding="utf-8"))["dependencies"][
        "@fission-ai/openspec"
    ]
    lock = json.loads((tools / "package-lock.json").read_text(encoding="utf-8"))
    locked = lock["packages"]["node_modules/@fission-ai/openspec"]["version"]
    readme = re.findall(r"@fission-ai/openspec@(\S+)", (ROOT / "README.md").read_text("utf-8"))
    generated = {
        m
        for skill in (ROOT / ".agents" / "skills").glob("openspec-*/SKILL.md")
        for m in re.findall(r'generatedBy: "([^"]+)"', skill.read_text(encoding="utf-8"))
    }
    assert re.fullmatch(r"\d+\.\d+\.\d+", pinned), "pin an exact version"
    assert locked == pinned
    assert readme == [pinned]
    assert generated == {pinned}
