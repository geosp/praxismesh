"""A task that returns the most questions `finish_task` keeps leaves no history
payload over 64 KiB (Phase 3A persistence plan phase 01 task 3.3; R18, D9). The
session guard in conftest.py checks every Workflow of the suite the same way."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from temporalio.api.history.v1 import History

from common.blob_store.s3 import S3BlobStore
from common.persistence.repositories import RecordingBlobStore, make_engine
from common.schemas import TaskResult
from orchestrator.submit import prepare_task, start_task
from registry.loader import load_registry
from tests.support.fake_model import FakeModel
from tests.support.history_guard import check_since, large_payloads, runs_since
from tests.support.workers import running_workers

pytestmark = pytest.mark.integration

QUESTIONS = [f"Question {i:02d}: " + "q" * 487 for i in range(20)]  # 500 characters each


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeModel]:
    script = [
        {
            "tool": "finish_task",
            "args": {"status": "needs_input", "summary": "s" * 2000, "questions": QUESTIONS},
        }
    ]
    with FakeModel(script) as model:
        monkeypatch.setenv("VLLM_BASE_URL", model.base_url)
        yield model


async def test_twenty_long_questions_stay_under_the_limit(tmp_path: Path, fake: FakeModel) -> None:
    assert all(len(q) == 500 for q in QUESTIONS)
    since = datetime.now(UTC) - timedelta(seconds=5)
    async with running_workers(tmp_path) as client:
        engine = make_engine()
        s3 = S3BlobStore.from_env()
        await s3.ensure_bucket()
        start = await prepare_task(
            {"profile": "openai", "instructions": "Ask your questions."},
            load_registry(),
            RecordingBlobStore(s3, engine),
            base_dir=Path.cwd(),
        )
        await engine.dispose()
        handle = await start_task(client, start)
        result = TaskResult.model_validate(await handle.result())
        history = await handle.fetch_history()
        assert result.status == "needs_input" and result.questions == QUESTIONS
        assert large_payloads(start.task_id, History(events=history.events)) == []
        # The listing the session guard uses finds this run too.
        assert start.task_id in {wf for wf, _ in await runs_since(client, since)}
        found = [p for p in await check_since(client, since) if p.workflow_id == start.task_id]
        assert found == []
