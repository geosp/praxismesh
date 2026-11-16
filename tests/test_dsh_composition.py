"""The DSH composition patch: every feature in notes.md#r14 is off (R14; DSH
migration plan task 2.4). Composition-level checks; the live ones are in
tests/integration/test_dsh_capabilities.py."""

from __future__ import annotations

from typing import Any

import pytest
import yaml

from harness_activity.dsh import composition
from harness_activity.dsh.ledger import DSH_MAX_OUTPUT_TOKENS

PATCH: list[dict[str, Any]] = yaml.safe_load(composition.render("spark", 32768, 8080))
INSERTED: list[dict[str, Any]] = next(e["insert"] for e in PATCH if "insert" in e)


def entry(name: str) -> dict[str, Any]:
    (found,) = [e for e in PATCH if e.get("id") == name]
    return found


@pytest.mark.parametrize(
    "feature",
    [
        "jobs",
        "session-title",
        "mcp-resources",
        "compaction-basic",
        "image-offload",
        "tool-fs",
        "tool-working-directory",
        "persistent-bash",
        "persistent-pwsh",
        "llm-deepseek",
    ],
)
def test_feature_is_disabled(feature: str) -> None:
    assert entry(feature) == {"id": feature, "disabled": True}


def test_no_dsh_skill_plugin_is_inserted() -> None:
    """The `dsh-skill*` plugins and the skill tool stay out: skills come from the
    template bundle through the executor's read_file (D4)."""
    plugins = [p["name"] for p in INSERTED]
    assert not [p for p in plugins if p.startswith(composition.SKILL_PLUGIN_PREFIX)]
    assert composition.SKILL_TOOL_PLUGIN not in plugins


def test_no_skill_discovery_roots() -> None:
    """`includeDefaultRoots: false`: with no skill-filesystem plugin there is no
    discovery root at all, and nothing in the patch turns one on."""
    text = composition.render("spark", 32768, 8080)
    assert "includeDefaultRoots: true" not in text and "customSkillDirs" not in text
    assert "dsh-skill-filesystem" not in text


def test_no_delegation_and_one_tool_call_at_a_time() -> None:
    assert entry("agent-loop")["config"] == {"agents": [], "maxParallelToolCalls": 1}


def test_only_the_gateway_provider_and_one_mcp_client_are_added() -> None:
    assert [p["name"] for p in INSERTED] == [
        "@deepseek-ai/dsh-llm-pi-ai",
        "@deepseek-ai/dsh-mcp-client",
    ]
    provider = INSERTED[0]["config"]["providers"][composition.PROVIDER]
    assert provider["baseURL"] == "http://127.0.0.1:8080/v1"  # the loopback relay only
    assert provider["apiKeyEnv"] == composition.MODEL_KEY_ENV
    assert provider["retryPolicy"]["maxRetries"] == 0  # the ledger sees every request once
    assert [m["id"] for m in provider["models"]] == ["spark"]
    assert provider["models"][0]["maxTokens"] == DSH_MAX_OUTPUT_TOKENS
    assert provider["models"][0]["contextWindow"] == 32768
    client = INSERTED[1]["config"]
    assert client["serverName"] == composition.MCP_SERVER and client["transport"] == "stdio"
    assert client["args"] == ["/opt/dsh/mcp_bridge.py"]
    assert client["reconnect"] == {"enabled": False}


def test_patch_touches_nothing_else() -> None:
    ids = [e["id"] for e in PATCH if "id" in e]
    assert sorted(ids) == sorted([*composition.DISABLED, "sandbox-policy", "agent-loop"])
    assert entry("sandbox-policy")["config"]["mode"] == "workspace-write"
