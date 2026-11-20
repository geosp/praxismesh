"""Base model for PraxisMesh schemas: frozen and strict about unknown fields."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Slug = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$", max_length=64)
Harness = Literal["claude_sdk", "claude_cli", "openai_agents", "dsh"]
# §4.13's classes (Phase 3A persistence plan D3). `task` is the Phase 1-2 class:
# it stays so recorded payloads still decode (R5), and nothing writes it.
RetentionClass = Literal["ephemeral", "checkpoint", "transcript", "artifact", "audit", "task"]


class Strict(BaseModel):
    """Every schema forbids unknown fields, so a misspelled or injected field fails
    loudly instead of being ignored (plan §5)."""

    model_config = ConfigDict(extra="forbid", frozen=True)
