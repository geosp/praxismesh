"""The benchmark's DSH container helper cleans up after a failed start, and
labels what it starts (phase 03 impl review F188)."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import pytest

from tests.support import dsh_container


def test_failed_start_removes_its_attempt_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    attempts = tmp_path / "dsh-x"
    calls: list[tuple[str, ...]] = []

    def mkdtemp(prefix: str, dir: str) -> str:
        attempts.mkdir()
        return str(attempts)

    def docker(*args: str, check: bool = True, timeout: float = 60) -> object:
        calls.append(args)
        raise subprocess.CalledProcessError(125, ["docker", *args])

    monkeypatch.setattr(tempfile, "mkdtemp", mkdtemp)
    monkeypatch.setattr(dsh_container, "docker", docker)
    with pytest.raises(subprocess.CalledProcessError):
        dsh_container.start_container("image")
    assert not attempts.exists()
    assert "--label" in calls[0] and dsh_container.LABEL in calls[0]
