"""Capability schemas: `AgentProfile`, `WorkerTemplate`, `McpServer` (plan §4.10, §5).

Capabilities (model, MCP servers, skills, tools) live on templates only. Profiles
carry identity and task-level limits, and have no capability fields.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated, Literal

from pydantic import Field, model_validator

from common.schemas.base import Harness, Slug, Strict

Name = Annotated[str, Slug]


class McpServer(Strict):
    """A catalog entry for an MCP server a template may mount."""

    schema_version: Literal[1] = 1
    name: Name
    transport: Literal["stdio", "sidecar", "service"]
    command: str | None = None
    args: list[str] = []
    env: dict[str, str] = {}
    # Names of infra/.env variables passed to this server only; each must also be
    # listed in the template's `secret_refs`.
    secret_env: list[str] = []
    tools_allowed: list[str] = Field(min_length=1)
    capabilities: list[str] = []
    client_session_timeout_seconds: float = Field(default=5.0, gt=0)

    @model_validator(mode="after")
    def _stdio_needs_command(self) -> McpServer:
        if self.transport == "stdio" and not self.command:
            raise ValueError("a stdio MCP server needs a command")
        return self


class WorkerTemplate(Strict):
    """The unit of capability: what a worker runs and what its agent may use."""

    schema_version: Literal[1] = 1
    name: Name
    version: int = Field(ge=1)
    tier: Name
    harness: Harness
    model: str = Field(min_length=1, pattern=r"^[^/]+$")
    base_url_env: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$")
    api_style: Literal["openai", "anthropic"]
    allowed_model_overrides: list[str] = []
    system_prompt: str = Field(description="Path of the prompt file, relative to registry/")
    mcp_servers: list[Name] = []
    skills_bundle: Name | None = None
    cli_tools: list[str] = []
    inner_max_turns: int = Field(ge=1)
    turn_timeout: timedelta
    heartbeat_timeout: timedelta
    max_turns_cap: int = Field(ge=1)
    max_tokens_cap: int = Field(ge=1)
    max_wall_time_cap: timedelta
    secret_refs: list[str] = []
    concurrency_per_pod: int = Field(default=1, ge=1)
    # Stored, unused until Phase 7 (plan §5 resource and scaling fields).
    resources: dict[str, str] = {}
    scaling: dict[str, int] = {}
    repo_capable: bool = False
    cost_weight: float = 1.0

    @property
    def ref(self) -> str:
        return f"{self.name}@{self.version}"

    @property
    def capabilities(self) -> list[str]:
        """Derived for audit: everything this template grants (plan §4.10)."""
        caps = [f"mcp:{name}" for name in self.mcp_servers]
        caps += [f"skills:{self.skills_bundle}"] if self.skills_bundle else []
        caps += [f"cli:{tool}" for tool in self.cli_tools]
        return caps


class AgentProfile(Strict):
    """Who the agent is and its task-level limits. No MCP or skills fields."""

    schema_version: Literal[1] = 1
    name: Name
    tier: Name
    harness: Harness
    model_override: str | None = None
    allowed_templates: list[Name] = Field(min_length=1)
    max_turns: int = Field(ge=1)
    max_tokens: int = Field(ge=1)
    max_wall_time: timedelta
    new_repo_policy: Literal["never", "ask", "auto"] = "ask"
    repo: str | None = None
