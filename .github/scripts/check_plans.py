"""Validate PraxisMesh plan contracts without private skills or script execution.

This checks repository-specific structure and completion evidence references. It
cannot establish that a review, acceptance suite or demo actually passed; the
fresh-session and coordinator gates in docs/reviews/README.md remain mandatory.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
REQUIRED = ("Summary", "Why", "What changes", "Requirements", "Decisions", "Impact", "Phases")
SHA = re.compile(r"[0-9a-f]{40}")


def frontmatter(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    match = re.fullmatch(r"---\n(.*?)\n---\n(.*)", text, re.DOTALL)
    if match is None:
        raise ValueError("missing YAML frontmatter")
    data = yaml.safe_load(match[1])
    if not isinstance(data, dict):
        raise ValueError("frontmatter must be a mapping")
    return data, match[2]


def validate_plan(folder: Path, repository: Path = ROOT) -> list[str]:
    errors: list[str] = []
    try:
        plan, body = frontmatter(folder / "plan.md")
        for heading in REQUIRED:
            if f"## {heading}\n" not in body:
                errors.append(f"missing section: {heading}")
        if plan.get("status") not in {
            "draft",
            "approved",
            "in-progress",
            "implemented",
            "closed",
            "abandoned",
        }:
            errors.append("invalid plan status")
        requirements = set(re.findall(r"^### (R\d+) [·:-]", body, re.MULTILINE))
        if not requirements:
            errors.append("no requirements")
        for section in re.split(r"^### R\d+ [·:-]", body, flags=re.MULTILINE)[1:]:
            content = section.split("\n## ", 1)[0]
            if not re.search(r"\*\*Given\*\*.*\*\*when\*\*.*\*\*then\*\*", content):
                errors.append("requirement has no Given/when/then scenario")
        phases = sorted((folder / "phases").glob("[0-9][0-9]-*.md"))
        if not phases:
            errors.append("no phase files")
        delivered: set[str] = set()
        for path in phases:
            phase, tasks = frontmatter(path)
            ids = phase.get("delivers")
            if not isinstance(ids, list) or not ids or not all(isinstance(i, str) for i in ids):
                errors.append(f"{path.name}: delivers must be a non-empty list of requirement IDs")
                continue
            delivered.update(ids)
            if not set(ids) <= requirements:
                errors.append(f"{path.name}: undefined delivered requirement")
            if phase.get("status") not in {
                "draft",
                "approved",
                "in-progress",
                "impl-reviewed",
                "done",
                "abandoned",
            }:
                errors.append(f"{path.name}: invalid phase status")
            task_lines = re.findall(r"^- \[[ xX]\] .*", tasks, re.MULTILINE)
            if not task_lines or any("Verify:" not in task for task in task_lines):
                errors.append(f"{path.name}: tasks need explicit Verify steps")
            if phase.get("status") == "done":
                if not phase.get("approved") or "- [ ]" in tasks:
                    errors.append(f"{path.name}: done requires approval and completed tasks")
                for gate in ("design_review", "impl_review", "verification", "demo"):
                    evidence = phase.get(gate)
                    if not isinstance(evidence, dict) or evidence.get("status") != "passed":
                        errors.append(f"{path.name}: done requires passed {gate}")
                refs = phase.get("evidence")
                if not isinstance(refs, dict) or not SHA.fullmatch(str(refs.get("code_sha", ""))):
                    errors.append(f"{path.name}: done requires immutable code_sha")
                else:
                    for key in ("review", "verification", "demo"):
                        reference = refs.get(key)
                        target = repository / str(reference or "")
                        if not reference or not target.resolve().is_relative_to(
                            repository.resolve()
                        ):
                            errors.append(f"{path.name}: invalid {key} evidence path")
                        elif not target.is_file():
                            errors.append(f"{path.name}: missing {key} evidence file")
        if delivered != requirements:
            errors.append("requirements must be delivered by phases")
        if not (folder / "reviews.md").is_file():
            errors.append("missing reviews.md")
    except (OSError, ValueError, yaml.YAMLError) as error:
        errors.append(str(error))
    return errors


def main() -> int:
    folders = sorted(path.parent for path in (ROOT / "docs/plans").glob("*/plan.md"))
    if not folders:
        print("No implementation plans found", file=sys.stderr)
        return 1
    failures = [(folder, problem) for folder in folders for problem in validate_plan(folder)]
    for folder, problem in failures:
        print(f"{folder.relative_to(ROOT)}: {problem}", file=sys.stderr)
    print(f"Validated {len(folders)} implementation plan(s); {len(failures)} error(s)")
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
