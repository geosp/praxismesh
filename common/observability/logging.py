"""JSON logs that carry the IDs needed to follow a task (RFC Phase 1, Observability).

IDs are held in a context variable, set with `log_context(...)` around a unit of
work, and added to every line. Conversation IDs arrive with Phase 2.
"""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Any

CONTEXT_FIELDS = ("request_id", "task_id", "workflow_id", "turn", "attempt", "worker")
_EMPTY: MappingProxyType[str, Any] = MappingProxyType({})
_context: ContextVar[MappingProxyType[str, Any]] = ContextVar("praxis_log_context", default=_EMPTY)


@contextmanager
def log_context(**ids: Any) -> Iterator[None]:
    """Add IDs to every log line written inside the block."""
    merged = {**_context.get(), **{k: v for k, v in ids.items() if v is not None}}
    token = _context.set(MappingProxyType(merged))
    try:
        yield
    finally:
        _context.reset(token)


def current_context() -> dict[str, Any]:
    return dict(_context.get())


# Attach the IDs to each record when it is created, not when it is formatted: a
# handler may format later, outside the block that set them.
_base_factory = logging.getLogRecordFactory()


def _record_with_context(*args: Any, **kwargs: Any) -> logging.LogRecord:
    record = _base_factory(*args, **kwargs)
    record.praxis_context = dict(_context.get())
    return record


logging.setLogRecordFactory(_record_with_context)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        line: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "msg": record.getMessage(),
            **getattr(record, "praxis_context", _context.get()),
        }
        extra = getattr(record, "fields", None)
        if isinstance(extra, dict):
            line.update(extra)
        if record.exc_info:
            line["exc"] = self.formatException(record.exc_info)
        return json.dumps(line, default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
