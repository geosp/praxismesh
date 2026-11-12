"""Worker metrics in Prometheus format (RFC Phase 1, Observability)."""

from __future__ import annotations

from prometheus_client import Counter, Histogram, start_http_server

ACTIVITY_SECONDS = Histogram(
    "praxis_activity_seconds", "Activity duration", ["activity", "outcome"]
)
HEARTBEAT_LAG_SECONDS = Histogram(
    "praxis_heartbeat_lag_seconds", "Time between an Activity's heartbeats", ["activity"]
)
TOKENS = Counter("praxis_tokens_total", "Model tokens", ["template", "direction"])
TOOL_CALLS = Counter("praxis_tool_calls_total", "Tool calls", ["template", "tool"])
TOOL_ERRORS = Counter("praxis_tool_errors_total", "Tool calls that failed", ["template", "tool"])
CHECKPOINT_BYTES = Histogram(
    "praxis_checkpoint_bytes",
    "Workspace snapshot size",
    buckets=(1e3, 1e4, 1e5, 1e6, 1e7, 5e7, 1e8),
)
CHECKPOINT_SECONDS = Histogram("praxis_checkpoint_seconds", "Time to take a checkpoint")


def serve_metrics(port: int) -> None:
    """Serve `/metrics` on `port` (0.0.0.0) from a background thread."""
    start_http_server(port)
