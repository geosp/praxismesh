"""The spike's `AgentEvent` copy keeps the root schema's fields (plan D1)."""

from __future__ import annotations

import ast
from pathlib import Path

from event_transport.models import AgentEvent

ROOT_SCHEMA = Path(__file__).resolve().parents[3] / "common" / "schemas" / "events.py"


def root_fields() -> list[str]:
    tree = ast.parse(ROOT_SCHEMA.read_text())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "AgentEvent")
    return [s.target.id for s in cls.body if isinstance(s, ast.AnnAssign) and isinstance(s.target, ast.Name)]


def test_copy_matches_the_root_schema() -> None:
    assert list(AgentEvent.model_fields) == root_fields()
