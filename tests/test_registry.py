"""Capability model: loaders, the lock, template-only capabilities
(spec agents/capability-model)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from common.errors import CapabilityError, InvalidTaskInput, RegistryError
from orchestrator.requests import parse_task_request
from registry.loader import REGISTRY_ROOT, load_registry
from registry.lock import update


@pytest.fixture
def registry_copy(tmp_path: Path) -> Path:
    root = tmp_path / "registry"
    shutil.copytree(REGISTRY_ROOT, root, ignore=shutil.ignore_patterns("*.py", "__pycache__"))
    return root


def test_loaders() -> None:
    registry = load_registry()
    profile, loaded = registry.resolve("default")
    assert profile.name == "default"
    assert loaded.template.ref == "local-default@1"
    assert loaded.hash.startswith("sha256:")
    assert "sample-shop" in registry.mcp_servers
    assert "order-desk" in registry.skills
    assert loaded.template.capabilities[0] == "mcp:sample-shop"


def test_registry_lock_is_current() -> None:
    assert update(REGISTRY_ROOT, check=True) == []


def test_changed_template_without_version_bump(registry_copy: Path) -> None:
    template = registry_copy / "templates" / "local-default.yaml"
    template.write_text(template.read_text().replace("inner_max_turns: 8", "inner_max_turns: 9"))
    with pytest.raises(RegistryError, match="changed but its version did not"):
        load_registry(registry_copy)


def test_changed_prompt_without_version_bump(registry_copy: Path) -> None:
    prompt = registry_copy / "prompts" / "local-default.md"
    prompt.write_text(prompt.read_text() + "\nAlso be brief.\n")
    with pytest.raises(RegistryError, match="changed but its version did not"):
        load_registry(registry_copy)


def test_new_version_needs_lock_entry(registry_copy: Path) -> None:
    template = registry_copy / "templates" / "local-default.yaml"
    template.write_text(
        template.read_text()
        .replace("version: 1", "version: 2")
        .replace("inner_max_turns: 8", "inner_max_turns: 9")
    )
    with pytest.raises(RegistryError, match=r"not in registry\.lock"):
        load_registry(registry_copy)
    assert update(registry_copy, check=False) == []
    assert load_registry(registry_copy).templates["local-default"].template.version == 2


def test_lock_never_rewrites_an_existing_version(registry_copy: Path) -> None:
    template = registry_copy / "templates" / "local-default.yaml"
    template.write_text(template.read_text().replace("inner_max_turns: 8", "inner_max_turns: 9"))
    assert any("changed under an existing version" in p for p in update(registry_copy, check=False))


@pytest.mark.parametrize("field", ["mcp_servers", "skills", "tools"])
def test_profile_rejects_capability_fields(registry_copy: Path, field: str) -> None:
    profile = registry_copy / "profiles" / "default.yaml"
    profile.write_text(profile.read_text() + f"{field}: [anything]\n")
    with pytest.raises(RegistryError, match=field):
        load_registry(registry_copy)


@pytest.mark.parametrize("field", ["skills", "mcp_servers", "tools", "allowed_tools", "model"])
def test_request_rejects_capability_fields(field: str) -> None:
    with pytest.raises(CapabilityError, match=field):
        parse_task_request({"profile": "default", "instructions": "x", field: ["rogue"]})


def test_request_rejects_unknown_and_unsafe_fields() -> None:
    with pytest.raises(InvalidTaskInput, match="colour"):
        parse_task_request({"profile": "default", "instructions": "x", "colour": "red"})
    with pytest.raises(InvalidTaskInput, match="outputs"):
        parse_task_request({"profile": "default", "instructions": "x", "outputs": ["../etc"]})


def test_harness_mismatch(registry_copy: Path) -> None:
    profile = registry_copy / "profiles" / "default.yaml"
    profile.write_text(profile.read_text().replace("harness: openai_agents", "harness: claude_sdk"))
    with pytest.raises(CapabilityError, match=r"claude_sdk.*openai_agents"):
        load_registry(registry_copy).resolve("default")


def test_template_must_be_allowed() -> None:
    with pytest.raises(CapabilityError, match="may not use template"):
        load_registry().resolve("default", "other-template")


def test_unsupported_harness_template_rejected(registry_copy: Path) -> None:
    template = registry_copy / "templates" / "local-default.yaml"
    template.write_text(
        template.read_text().replace("harness: openai_agents", "harness: claude_sdk")
    )
    with pytest.raises(RegistryError, match="no runner in this phase"):
        load_registry(registry_copy, check_lock=False)


def test_mcp_secret_must_be_granted_by_template(registry_copy: Path) -> None:
    template = registry_copy / "templates" / "local-default.yaml"
    template.write_text(
        template.read_text().replace("secret_refs: [PRAXIS_SAMPLE_DB_URL]", "secret_refs: []")
    )
    with pytest.raises(RegistryError, match="needs secret_refs"):
        load_registry(registry_copy, check_lock=False)
