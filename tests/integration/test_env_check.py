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


@pytest.mark.parametrize(
    ("line", "replacement"),
    [
        ("APP_DB_PASSWORD=change-me-app", 'APP_DB_PASSWORD="s3cr#t"'),
        ("APP_DB_PASSWORD=change-me-app", "APP_DB_PASSWORD=a$b"),
        ("APP_DB_PASSWORD=change-me-app", "APP_DB_PASSWORD=two words"),
    ],
)
def test_value_syntax_rejected(tmp_path: Path, line: str, replacement: str) -> None:
    """Make, Compose and the check read only plain KEY=value lines the same way."""
    env_file = tmp_path / ".env"
    env_file.write_text(EXAMPLE.read_text().replace(line, replacement))
    result = check(env_file)
    assert result.returncode == 1
    assert "use KEY=value with no quotes" in result.stderr


def test_empty_optional_variable(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(EXAMPLE.read_text().replace("TEMPORAL_PORT=7233", "TEMPORAL_PORT="))
    result = check(env_file)
    assert result.returncode == 1
    assert "TEMPORAL_PORT is not set" in result.stderr


def test_retention_format(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        EXAMPLE.read_text().replace("TEMPORAL_RETENTION=72h", "TEMPORAL_RETENTION=3")
    )
    result = check(env_file)
    assert result.returncode == 1
    assert "TEMPORAL_RETENTION must be <number><s|m|h|d>" in result.stderr


def test_make_up_runs_the_check(tmp_path: Path) -> None:
    """`make up` stops at the check, before Compose, when infra/.env is missing."""
    missing = tmp_path / "missing.env"
    result = subprocess.run(
        ["make", "--no-print-directory", "up", f"ENV_FILE={missing}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "missing.env is missing" in result.stderr
