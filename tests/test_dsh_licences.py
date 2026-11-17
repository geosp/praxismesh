"""Every pinned DSH distribution has its licence notices, and the check fails
when one is removed or left behind (DSH migration plan R20)."""

from __future__ import annotations

import shutil
from pathlib import Path

import check_dsh_licences as licences
import pytest


def test_every_pinned_distribution_has_notices() -> None:
    assert licences.pinned(), "infra/dsh/requirements.txt pins nothing"
    assert licences.check() == []


def copy_notices(tmp_path: Path) -> Path:
    notices = tmp_path / "docs" / "licences" / "dsh"
    shutil.copytree(licences.NOTICES, notices)
    return notices


def test_a_removed_notice_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(licences, "ROOT", tmp_path)
    notices = copy_notices(tmp_path)
    dist = licences.pinned()[0]
    shutil.rmtree(notices / dist)
    errors = licences.check(notices=notices)
    assert len(errors) == 1 and errors[0].startswith(f"{dist}: no licence notices")


def test_an_empty_notice_directory_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(licences, "ROOT", tmp_path)
    notices = copy_notices(tmp_path)
    dist = licences.pinned()[0]
    for f in (notices / dist).iterdir():
        f.unlink()
    assert licences.check(notices=notices) == [
        f"{dist}: docs/licences/dsh/{dist} has no notice file"
    ]


def test_unpinned_notices_fail(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(licences, "ROOT", tmp_path)
    notices = copy_notices(tmp_path)
    (notices / "left-behind-1.0").mkdir()
    (notices / "left-behind-1.0" / "LICENSE").write_text("MIT")
    errors = licences.check(notices=notices)
    assert errors == ["left-behind-1.0: notices for a distribution that is no longer pinned"]


def test_pins_are_normalised() -> None:
    names = licences.pinned()
    assert any(n.startswith("pydantic-core-") for n in names)  # pinned as pydantic-core
    assert all(n == n.lower() and "_" not in n.rsplit("-", 1)[0] for n in names)
