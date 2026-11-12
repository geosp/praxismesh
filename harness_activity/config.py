"""Harness configuration, built only from the worker template (plan §4.1, §4.10)."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from common.errors import CapabilityError
from registry.loader import LoadedTemplate, Registry


@dataclass(frozen=True)
class McpConfig:
    name: str
    command: str
    args: list[str]
    env: dict[str, str]
    tools_allowed: list[str]
    timeout_s: float


@dataclass(frozen=True)
class HarnessConfig:
    template_ref: str
    template_hash: str
    model: str
    base_url: str
    api_key: str
    instructions: str
    inner_max_turns: int
    cli_tools: list[str]
    skills_bundle: Path | None
    mcp: list[McpConfig] = field(default_factory=list)


def build_config(registry: Registry, loaded: LoadedTemplate, task_id: str) -> HarnessConfig:
    template = loaded.template
    base_url = os.environ.get(template.base_url_env, "")
    if not base_url:
        raise CapabilityError(f"{template.base_url_env} is not set for template {template.ref}")
    servers = []
    for name in template.mcp_servers:
        server = registry.mcp_servers[name]
        if server.transport != "stdio" or not server.command:
            raise CapabilityError(f"MCP server {name!r}: only stdio is supported in Phase 1")
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "LANG": "C.UTF-8",
            **server.env,
            "PRAXIS_TASK_ID": task_id,
        }
        for var in server.secret_env:  # granted by the template (checked when loaded)
            env[var] = os.environ.get(var, "")
        command = sys.executable if server.command == "python" else server.command
        servers.append(
            McpConfig(
                name,
                command,
                list(server.args),
                env,
                list(server.tools_allowed),
                server.client_session_timeout_seconds,
            )
        )
    bundle = registry.skills.get(template.skills_bundle) if template.skills_bundle else None
    return HarnessConfig(
        template_ref=template.ref,
        template_hash=loaded.hash,
        model=template.model,
        base_url=base_url.rstrip("/"),
        api_key=os.environ.get("VLLM_API_KEY", "") or "not-needed",
        instructions=loaded.system_prompt,
        inner_max_turns=template.inner_max_turns,
        cli_tools=list(template.cli_tools),
        skills_bundle=bundle,
        mcp=servers,
    )
