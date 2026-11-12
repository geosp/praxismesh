"""Load and validate the registry: profiles, templates, the MCP catalog and skills
(plan §4.10, §5; RFC Phase 1, Capability model).

A template is identified by `name@version`. `registry/registry.lock` records the
sha256 of each template file together with its system prompt; a changed file
under an existing version, or a template missing from the lock, fails to load.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeVar

import yaml
from pydantic import BaseModel, ValidationError

from common.errors import CapabilityError, RegistryError
from common.schemas import AgentProfile, McpServer, WorkerTemplate

REGISTRY_ROOT = Path(__file__).resolve().parent
LOCK_FILE = "registry.lock"
# Harnesses with a runner in this phase (Phase 1: openai_agents only; the Claude
# Agent SDK runner is deferred, decision log 2026-11-11).
SUPPORTED_HARNESSES = frozenset({"openai_agents"})

M = TypeVar("M", bound=BaseModel)


def _load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict):
        raise RegistryError(f"{path}: expected a mapping")
    return data


def _parse(model: type[M], path: Path) -> M:
    try:
        return model.model_validate(_load_yaml(path))
    except ValidationError as e:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in e.errors()
        )
        raise RegistryError(f"{path}: {problems}") from e


def template_hash(root: Path, template_file: Path, template: WorkerTemplate) -> str:
    """sha256 over the template file and its system prompt."""
    digest = hashlib.sha256(template_file.read_bytes())
    digest.update(b"\0")
    digest.update((root / template.system_prompt).read_bytes())
    return f"sha256:{digest.hexdigest()}"


def read_lock(root: Path) -> dict[str, str]:
    path = root / LOCK_FILE
    if not path.exists():
        return {}
    templates = _load_yaml(path).get("templates") or {}
    if not isinstance(templates, dict):
        raise RegistryError(f"{path}: `templates` must be a mapping")
    return {str(k): str(v) for k, v in templates.items()}


@dataclass(frozen=True)
class LoadedTemplate:
    template: WorkerTemplate
    hash: str
    system_prompt: str


@dataclass(frozen=True)
class Registry:
    root: Path
    profiles: dict[str, AgentProfile] = field(default_factory=dict)
    templates: dict[str, LoadedTemplate] = field(default_factory=dict)
    mcp_servers: dict[str, McpServer] = field(default_factory=dict)
    skills: dict[str, Path] = field(default_factory=dict)

    def resolve(
        self, profile_name: str, template_name: str | None = None
    ) -> tuple[AgentProfile, LoadedTemplate]:
        """Choose the template for a task and check the profile may use it."""
        profile = self.profiles.get(profile_name)
        if profile is None:
            raise CapabilityError(f"unknown profile {profile_name!r}")
        name = template_name or profile.allowed_templates[0]
        if name not in profile.allowed_templates:
            raise CapabilityError(
                f"profile {profile.name!r} may not use template {name!r} "
                f"(allowed: {', '.join(profile.allowed_templates)})"
            )
        loaded = self.templates.get(name)
        if loaded is None:
            raise CapabilityError(f"unknown template {name!r}")
        template = loaded.template
        if profile.harness != template.harness:
            raise CapabilityError(
                f"profile {profile.name!r} harness {profile.harness!r} does not match "
                f"template {template.ref!r} harness {template.harness!r}"
            )
        override = profile.model_override
        if override and override not in template.allowed_model_overrides:
            raise CapabilityError(
                f"profile {profile.name!r} model_override {override!r} is not allowed "
                f"by template {template.ref!r}"
            )
        return profile, loaded


def load_registry(root: Path = REGISTRY_ROOT, *, check_lock: bool = True) -> Registry:
    """Load every definition under `root` and check templates against the lock."""
    mcp = {s.name: s for s in (_parse(McpServer, p) for p in sorted(root.glob("mcp/*.yaml")))}
    skills = {p.parent.name: p.parent for p in sorted(root.glob("skills/*/SKILL.md"))}
    profiles = {
        p.name: p for p in (_parse(AgentProfile, f) for f in sorted(root.glob("profiles/*.yaml")))
    }
    lock = read_lock(root) if check_lock else {}
    templates: dict[str, LoadedTemplate] = {}
    for path in sorted(root.glob("templates/*.yaml")):
        template = _parse(WorkerTemplate, path)
        if template.name in templates:
            raise RegistryError(f"{path}: template {template.name!r} is defined twice")
        if template.harness not in SUPPORTED_HARNESSES:
            raise RegistryError(
                f"{path}: harness {template.harness!r} has no runner in this phase "
                f"(supported: {', '.join(sorted(SUPPORTED_HARNESSES))})"
            )
        prompt = root / template.system_prompt
        if not prompt.is_file():
            raise RegistryError(f"{path}: system prompt {template.system_prompt!r} not found")
        for server in template.mcp_servers:
            if server not in mcp:
                raise RegistryError(f"{path}: unknown MCP server {server!r}")
            missing = set(mcp[server].secret_env) - set(template.secret_refs)
            if missing:
                raise RegistryError(
                    f"{path}: MCP server {server!r} needs secret_refs {sorted(missing)}"
                )
        if template.skills_bundle and template.skills_bundle not in skills:
            raise RegistryError(f"{path}: unknown skills bundle {template.skills_bundle!r}")
        digest = template_hash(root, path, template)
        if check_lock:
            locked = lock.get(template.ref)
            if locked is None:
                raise RegistryError(
                    f"{path}: template {template.ref} is not in {LOCK_FILE}; "
                    "bump the version if needed and run `make registry-lock`"
                )
            if locked != digest:
                raise RegistryError(
                    f"{path}: template {template.ref} changed but its version did not; "
                    "bump `version` and run `make registry-lock`"
                )
        templates[template.name] = LoadedTemplate(template, digest, prompt.read_text())
    for profile in profiles.values():
        for name in profile.allowed_templates:
            if name not in templates:
                raise RegistryError(f"profile {profile.name!r}: unknown template {name!r}")
    return Registry(root, profiles, templates, mcp, skills)
