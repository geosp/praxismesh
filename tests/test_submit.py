"""Preparing a task: validation before any Workflow starts, minted IDs, and the
instructions and inputs stored as blobs (spec agents/capability-model;
RFC TaskWorkflow, starting a task)."""

from __future__ import annotations

from pathlib import Path

import pytest

from common.blob_store import MemoryBlobStore
from common.errors import CapabilityError, InvalidTaskInput
from orchestrator.submit import prepare_task
from registry.loader import load_registry


async def test_prepare_task(tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text("SKU-1 x3")
    blobs = MemoryBlobStore()
    start = await prepare_task(
        {
            "profile": "default",
            "instructions": "Order it.",
            "input_files": ["notes.txt"],
            "outputs": ["order-summary.md"],
        },
        load_registry(),
        blobs,
        base_dir=tmp_path,
    )
    assert start.task_id.startswith("task-") and start.request_id.startswith("req-")
    assert start.template == "local-default"
    assert await blobs.get(start.instructions_ref) == b"Order it."
    assert await blobs.get(start.input_refs["notes.txt"]) == b"SKU-1 x3"
    assert start.instructions_ref.retention_class == "task"
    assert start.outputs == ["order-summary.md"]


async def test_forbidden_skill_or_tool_rejected_before_start(tmp_path: Path) -> None:
    blobs = MemoryBlobStore()
    with pytest.raises(CapabilityError, match="skills"):
        await prepare_task(
            {"profile": "default", "instructions": "x", "skills": ["rogue"]},
            load_registry(),
            blobs,
            base_dir=tmp_path,
        )
    assert blobs.objects == {}  # nothing stored, nothing started


async def test_missing_input_file(tmp_path: Path) -> None:
    with pytest.raises(InvalidTaskInput, match=r"missing\.txt"):
        await prepare_task(
            {"profile": "default", "instructions": "x", "input_files": ["missing.txt"]},
            load_registry(),
            MemoryBlobStore(),
            base_dir=tmp_path,
        )


async def test_given_task_id_is_kept(tmp_path: Path) -> None:
    start = await prepare_task(
        {"profile": "default", "instructions": "x", "task_id": "task-demo-0001"},
        load_registry(),
        MemoryBlobStore(),
        base_dir=tmp_path,
    )
    assert start.task_id == "task-demo-0001"
