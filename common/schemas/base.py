"""Base model for PraxisMesh schemas: frozen and strict about unknown fields."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Slug = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$", max_length=64)
Harness = Literal["claude_sdk", "claude_cli", "openai_agents"]
RetentionClass = Literal["ephemeral", "task", "audit"]


class Strict(BaseModel):
    """Every schema forbids unknown fields, so a misspelled or injected field fails
    loudly instead of being ignored (plan §5)."""

    model_config = ConfigDict(extra="forbid", frozen=True)
