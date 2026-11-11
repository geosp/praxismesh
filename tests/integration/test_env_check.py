"""`make up`'s prerequisite check names what is missing (local-stack spec)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "infra" / "check-prereqs.sh"
EXAMPLE = ROOT / "infra" / ".env.example"


def check(env_file: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["sh", str(SCRIPT), str(env_file)], capture_output=True, text=True, check=False
    )


def test_example_passes(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(EXAMPLE.read_text())
    result = check(env_file)
    assert result.returncode == 0, result.stderr


def test_missing_env_file(tmp_path: Path) -> None:
    result = check(tmp_path / "missing.env")
    assert result.returncode == 1
    assert "missing.env is missing" in result.stderr
    assert "cp infra/.env.example" in result.stderr


def test_unset_variable(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    text = EXAMPLE.read_text().replace("APP_DB_PASSWORD=change-me-app", "APP_DB_PASSWORD=")
    env_file.write_text(text)
    result = check(env_file)
    assert result.returncode == 1
    assert "APP_DB_PASSWORD is not set" in result.stderr


def test_model_name_with_slash(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(EXAMPLE.read_text().replace("VLLM_MODEL=spark", "VLLM_MODEL=org/model"))
    result = check(env_file)
    assert result.returncode == 1
    assert "VLLM_MODEL must not contain '/'" in result.stderr
