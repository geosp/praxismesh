"""Public plan contracts preserve coverage and cannot claim unverified closure."""

from __future__ import annotations

import shutil
from pathlib import Path

import check_plans
import pytest

SOURCE = Path(__file__).resolve().parents[1] / "docs/plans/2026-11-13-skill-central-migration"


@pytest.fixture
def contract(tmp_path: Path) -> Path:
    folder = tmp_path / "contract"
    shutil.copytree(SOURCE, folder)
    return folder


def replace(path: Path, old: str, new: str) -> None:
    path.write_text(path.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")


def test_draft_contract_is_valid_without_private_skills(contract: Path) -> None:
    assert check_plans.validate_plan(contract, contract.parent) == []


def test_undefined_requirement_is_rejected(contract: Path) -> None:
    phase = next((contract / "phases").glob("01-*.md"))
    replace(phase, "delivers: [R1, R2]", "delivers: [R99]")
    assert any("undefined delivered" in e for e in check_plans.validate_plan(contract))


def test_requirement_without_scenario_is_rejected(contract: Path) -> None:
    replace(contract / "plan.md", "**Given**", "Given")
    assert any("no Given/when/then" in e for e in check_plans.validate_plan(contract))


def test_done_requires_review_verification_demo_and_evidence(contract: Path) -> None:
    phase = next((contract / "phases").glob("01-*.md"))
    replace(phase, "status: draft", "status: done")
    errors = check_plans.validate_plan(contract)
    assert any("approval and completed tasks" in e for e in errors)
    for gate in ("design_review", "impl_review", "verification", "demo"):
        assert any(f"passed {gate}" in e for e in errors)
    assert any("immutable code_sha" in e for e in errors)


def test_done_rejects_evidence_outside_repository(contract: Path) -> None:
    phase = next((contract / "phases").glob("01-*.md"))
    replace(phase, "status: draft", "status: done")
    with phase.open("r+", encoding="utf-8") as stream:
        text = stream.read().replace(
            "approved: null",
            "approved: 2026-11-13\nevidence: {code_sha: "
            + "a" * 40
            + ", review: ../outside.md, verification: ../outside.md, demo: ../outside.md}",
        )
        stream.seek(0)
        stream.write(text)
        stream.truncate()
    assert any(
        "invalid review evidence" in e for e in check_plans.validate_plan(contract, contract)
    )


@pytest.mark.parametrize("status", ["implemented", "closed"])
def test_completed_parent_rejects_unfinished_phases(contract: Path, status: str) -> None:
    replace(contract / "plan.md", "status: draft", f"status: {status}")
    assert any("unfinished phase" in e for e in check_plans.validate_plan(contract))


@pytest.mark.parametrize("status", ["implemented", "closed"])
def test_completed_parent_allows_explicitly_abandoned_phases(contract: Path, status: str) -> None:
    replace(contract / "plan.md", "status: draft", f"status: {status}")
    for phase in (contract / "phases").glob("[0-9][0-9]-*.md"):
        replace(phase, "status: draft", "status: abandoned")
    assert check_plans.validate_plan(contract) == []
