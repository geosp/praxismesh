"""gc's rules follow notes.md#d3 through `TABLE_CLASS`, its one source (Phase 3A
persistence plan D3; review F121)."""

from __future__ import annotations

from common.persistence.retention import DEFAULT_LIFETIME, TABLE_CLASS
from orchestrator import lifecycle

# Their rows leave through the event prune (D11), not a row rule.
PRUNED = {"event_logs", "agent_events"}


def test_every_expiring_table_has_a_gc_rule() -> None:
    expiring = {
        table
        for table, cls in TABLE_CLASS.items()
        if cls is not None and DEFAULT_LIFETIME[cls] is not None
    }
    ruled = {rule.table for rule in lifecycle.ROW_RULES}
    assert expiring - PRUNED == ruled
    assert lifecycle.EVENT_RETENTION == TABLE_CLASS["agent_events"] == TABLE_CLASS["event_logs"]


def test_rules_take_their_class_from_table_class() -> None:
    for rule in (*lifecycle.ROW_RULES, *lifecycle.DELETE_ROWS):
        assert rule.retention == TABLE_CLASS[rule.table], rule.table
