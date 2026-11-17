"""A DSH container for integration tests (DSH migration plan D3, ADR-0006).

The container itself is in `tests.support.dsh_container`, shared with the agent
benchmark; this module adds what only pytest needs.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from registry.loader import REGISTRY_ROOT
from registry.lock import update
from tests.support import dsh_container
from tests.support.dsh_container import (
    RUNTIME_UID,
    DshContainer,
    MemoryLedgerStore,
    docker,
    start_container,
)

__all__ = [
    "RUNTIME_UID",
    "DshContainer",
    "MemoryLedgerStore",
    "build_image",
    "docker",
    "make_dsh_registry",
    "start_container",
]


def make_dsh_registry(target: Path, **settings: object) -> Path:
    """A registry copy whose `local-dsh` template has other settings (a short
    heartbeat or turn timeout, a lower inner-turn limit), with its own lock."""
    shutil.copytree(REGISTRY_ROOT, target, ignore=shutil.ignore_patterns("*.py", "__pycache__"))
    template = target / "templates" / "local-dsh.yaml"
    template.write_text(
        yaml.safe_dump({**yaml.safe_load(template.read_text()), **settings}, sort_keys=False)
    )
    (target / "registry.lock").unlink()
    assert update(target, check=False) == []
    return target


def build_image() -> str:
    if shutil.which("docker") is None:
        pytest.skip("docker is not available")
    return dsh_container.build_image()
