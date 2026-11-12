"""`make up` checks infra/.env and names whatever is wrong (local-stack spec: Clear
diagnostics, Configuration without committed secrets). Each test runs `make up`
with a temporary env file, so the check must stop it before Compose starts."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "infra" / ".env.example"
EXAMPLE_TEXT = EXAMPLE.read_text()


# Point Docker at a socket that does not exist, so that even if a check
# regressed, these tests could never start, stop or reset a real stack.
NO_DOCKER = {"DOCKER_HOST": "unix:///nonexistent/docker.sock"}


def make(target: str, env_file: Path, *flags: str, **env: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["make", "--no-print-directory", *flags, target, f"ENV_FILE={env_file}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, **NO_DOCKER, **env},
    )


def env_file_with(tmp_path: Path, old: str, new: str) -> Path:
    assert old in EXAMPLE_TEXT
    path = tmp_path / ".env"
    path.write_text(EXAMPLE_TEXT.replace(old, new))
    return path


def line_of(path: Path, prefix: str) -> int:
    lines = path.read_text().splitlines()
    return next(i for i, line in enumerate(lines, 1) if line.startswith(prefix))


def test_example_passes(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_text(EXAMPLE_TEXT)
    result = subprocess.run(
        ["sh", "infra/check-prereqs.sh", str(path)], cwd=ROOT, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


def test_missing_env_file(tmp_path: Path) -> None:
    result = make("up", tmp_path / "missing.env")
    assert result.returncode != 0
    assert "missing.env is missing" in result.stderr
    assert "cp infra/.env.example" in result.stderr


@pytest.mark.parametrize("char", ['"', "'", " ", "#", "$", "\\", "`", ";", "&", "|", "(", "~"])
def test_value_character_rejected(tmp_path: Path, char: str) -> None:
    path = env_file_with(tmp_path, "APP_DB_PASSWORD=change-me-app", f"APP_DB_PASSWORD=ab{char}cd")
    result = make("up", path)
    assert result.returncode != 0
    n = line_of(path, "APP_DB_PASSWORD=")
    assert f"line {n}" in result.stderr


def test_comment_continuation_rejected(tmp_path: Path) -> None:
    """A comment ending in '\\' must not hide or join the next line."""
    path = env_file_with(tmp_path, "TEMPORAL_RETENTION=72h", "# note \\\nTEMPORAL_RETENTION=96h")
    result = make("up", path)
    assert result.returncode != 0
    assert f"line {line_of(path, '# note')}: a line must not end with" in result.stderr


@pytest.mark.parametrize("key", ["MAKEFLAGS", "SHELL", "ENV_FILE", "APP_DB_PASSWRD"])
def test_unknown_key_rejected(tmp_path: Path, key: str) -> None:
    path = env_file_with(tmp_path, "DB_PORT=5432", f"DB_PORT=5432\n{key}=x")
    result = make("up", path)
    assert result.returncode != 0
    assert f"line {line_of(path, key + '=')}: expected KEY=value with a known KEY" in result.stderr


def test_unset_variable(tmp_path: Path) -> None:
    path = env_file_with(tmp_path, "APP_DB_PASSWORD=change-me-app", "APP_DB_PASSWORD=")
    result = make("up", path)
    assert result.returncode != 0
    assert "APP_DB_PASSWORD is not set" in result.stderr


def test_empty_optional_variable(tmp_path: Path) -> None:
    path = env_file_with(tmp_path, "TEMPORAL_PORT=7233", "TEMPORAL_PORT=")
    result = make("up", path)
    assert result.returncode != 0
    assert "TEMPORAL_PORT is not set" in result.stderr


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("3", "must be <number><s|m|h|d>"),
        ("30m", "must be at least one day"),
        ("9999999999h", "must be <number><s|m|h|d>"),
    ],
)
def test_retention_rejected(tmp_path: Path, value: str, message: str) -> None:
    path = env_file_with(tmp_path, "TEMPORAL_RETENTION=72h", f"TEMPORAL_RETENTION={value}")
    result = make("up", path)
    assert result.returncode != 0
    assert message in result.stderr


def test_model_name_with_slash(tmp_path: Path) -> None:
    path = env_file_with(tmp_path, "VLLM_MODEL=spark", "VLLM_MODEL=org/model")
    result = make("up", path)
    assert result.returncode != 0
    assert "VLLM_MODEL must not contain '/'" in result.stderr


@pytest.mark.parametrize("name", ["", "Upper", "a b"])
def test_bad_project_name_rejected(tmp_path: Path, name: str) -> None:
    path = env_file_with(
        tmp_path, "COMPOSE_PROJECT_NAME=praxismesh", f"COMPOSE_PROJECT_NAME={name}"
    )
    result = make("up", path, COMPOSE_PROJECT_NAME="")
    assert result.returncode != 0
    assert "COMPOSE_PROJECT_NAME" in result.stderr


def test_reset_refuses_without_project_name(tmp_path: Path) -> None:
    """Never fall back to a default project: that could be another checkout's data."""
    result = make("reset", tmp_path / "missing.env", COMPOSE_PROJECT_NAME="")
    assert result.returncode != 0
    assert "refusing to guess which stack to act on" in result.stderr


def test_duplicate_key_rejected(tmp_path: Path) -> None:
    """Compose keeps the last value and uv the first, so a repeat is an error."""
    path = env_file_with(tmp_path, "DB_PORT=5432", "DB_PORT=5432\nDB_PORT=6543")
    result = make("up", path)
    assert result.returncode != 0
    lines = path.read_text().splitlines()
    n = len(lines) - lines[::-1].index("DB_PORT=6543")
    assert f"line {n}: DB_PORT is already set on an earlier line" in result.stderr


def project_flags(target: str, env_file: Path, **env: str) -> set[str]:
    """The project names `make -n <target>` would pass to Compose with `-p`."""
    return set(re.findall(r'-p "([^"]*)"', make(target, env_file, "-n", **env).stdout))


def test_shell_project_name_ignored(tmp_path: Path) -> None:
    """A COMPOSE_PROJECT_NAME left in the shell (for example by sourcing another
    checkout's infra/.env) must not redirect up, status, down or reset."""
    path = env_file_with(tmp_path, "COMPOSE_PROJECT_NAME=praxismesh", "COMPOSE_PROJECT_NAME=mine")
    for target in ("up", "down", "reset", "logs"):
        assert project_flags(target, path, COMPOSE_PROJECT_NAME="other") == {"mine"}, target


def test_up_and_reset_resolve_the_same_project(tmp_path: Path) -> None:
    path = env_file_with(tmp_path, "COMPOSE_PROJECT_NAME=praxismesh", "COMPOSE_PROJECT_NAME=mine")
    assert project_flags("up", path) == project_flags("reset", path) == {"mine"}
