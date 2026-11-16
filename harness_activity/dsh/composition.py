"""The DSH composition patch for one attempt (DSH migration plan R14, notes.md#r14).

DSH starts from its `sdk-minimal` profile. This patch turns off every DSH feature
that would give the process a capability the template did not grant, and adds
exactly two plugins: the model provider, which can only reach the worker's
gateway, and one MCP client, which presents the worker's tool catalog. No DSH
skill plugin is ever inserted: the template's skill bundle is mounted read-only
in the workspace and read through the executor's `read_file`.
"""

from __future__ import annotations

from typing import Any

import yaml

from harness_activity.dsh.ledger import DSH_MAX_OUTPUT_TOKENS

# Composition ids disabled outright (notes.md#r14; `llm-deepseek` is the hosted
# provider, replaced by the gateway-only provider below).
DISABLED = (
    "llm-deepseek",
    "jobs",
    "session-title",
    "mcp-resources",
    "compaction-basic",
    "image-offload",
    "tool-fs",
    "tool-working-directory",
    "persistent-bash",
    "persistent-pwsh",
)
# DSH's own skill plugins: never part of the patch (D4).
SKILL_PLUGIN_PREFIX = "@deepseek-ai/dsh-skill"
SKILL_TOOL_PLUGIN = "@deepseek-ai/dsh-tool-skill"
PROVIDER = "praxis-local"
MCP_SERVER = "praxis"
TOOL_PREFIX = f"mcp__{MCP_SERVER}__"
MODEL_KEY_ENV = "PRAXIS_MODEL_KEY"
RUNTIME_TREE = "/run/attempt"
DEFAULT_CONTEXT_WINDOW = 32768


def build(model: str, context_window: int | None, relay_port: int) -> list[dict[str, Any]]:
    window = context_window or DEFAULT_CONTEXT_WINDOW
    return [
        *({"id": name, "disabled": True} for name in DISABLED),
        {
            "id": "sandbox-policy",
            "config": {"mode": "workspace-write", "workspaceRoot": f"{RUNTIME_TREE}/workspace"},
        },
        # No sub-agents (no delegation), and one tool call at a time, so the
        # barrier never sees a tool running beside a held model request.
        {"id": "agent-loop", "config": {"agents": [], "maxParallelToolCalls": 1}},
        {
            "insert": [
                {
                    "id": "praxis-local-model",
                    "name": "@deepseek-ai/dsh-llm-pi-ai",
                    "config": {
                        "providers": {
                            PROVIDER: {
                                "api": "openai-completions",
                                "baseURL": f"http://127.0.0.1:{relay_port}/v1",
                                "apiKeyEnv": MODEL_KEY_ENV,
                                "defaultContextWindow": window,
                                "defaultMaxTokens": DSH_MAX_OUTPUT_TOKENS,
                                # The gateway ledger must see every request once.
                                "retryPolicy": {"mode": "normal", "maxRetries": 0},
                                "models": [
                                    {
                                        "id": model,
                                        "name": model,
                                        "contextWindow": window,
                                        "maxTokens": DSH_MAX_OUTPUT_TOKENS,
                                    }
                                ],
                            }
                        }
                    },
                },
                {
                    "id": "praxis-tools",
                    "name": "@deepseek-ai/dsh-mcp-client",
                    "config": {
                        "serverName": MCP_SERVER,
                        "transport": "stdio",
                        "command": "/usr/local/bin/python",
                        "args": ["/opt/dsh/mcp_bridge.py"],
                        "cwd": f"{RUNTIME_TREE}/workspace",
                        "startupTimeoutMs": 10000,
                        "toolCallTimeoutMs": 180000,
                        "failOnStartupError": True,
                        "reconnect": {"enabled": False},
                    },
                },
            ]
        },
    ]


def render(model: str, context_window: int | None, relay_port: int) -> str:
    return yaml.safe_dump(build(model, context_window, relay_port), sort_keys=False)
