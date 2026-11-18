"""Worker-side tool executor for one DSH attempt (DSH migration plan D4, R14, R16).

DSH is offered one MCP catalog and every call to it lands here, outside the DSH
container. The catalog is the production tool set: the `harness_activity.tools`
bodies, wrapped as they are for `openai_agents` so argument validation is the
same, and the template's MCP servers, started by the worker with the template's
environment and filtered by `tools_allowed`. File tools run against the shared
workspace; `run_command` runs in the attempt's cgroup through the launcher.

Every call is recorded and emits `tool_call` and `tool_result` events that carry
the tool name and status, never arguments or results.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

from agents.mcp import MCPServerStdio, create_static_tool_filter
from agents.tool import FunctionTool
from agents.tool_context import ToolContext

from common.observability.metrics import TOOL_CALLS, TOOL_ERRORS
from harness_activity.config import HarnessConfig
from harness_activity.dsh.gateway import Reply, json_reply
from harness_activity.events import STATUS_TOOL, AttemptEvents, emit_agent_status
from harness_activity.runner import Usage, looks_failed
from harness_activity.tools import FINISH_TOOL, CommandRunner, TurnState, build_tools

log = logging.getLogger("praxis.harness")
MCP_CALL_TIMEOUT_S = 120.0


def _invoke(tool: FunctionTool, call_id: str, payload: str) -> str:
    """Run a production tool wrapper in this thread, with its own event loop, so a
    blocking body (a command through the launcher) never blocks the worker's loop."""
    context = ToolContext(
        context=None, tool_name=tool.name, tool_call_id=call_id, tool_arguments=payload
    )

    async def call() -> str:
        return str(await tool.on_invoke_tool(context, payload))

    return asyncio.run(call())


class Executor:
    def __init__(
        self,
        workspace: Path,
        config: HarnessConfig,
        run_command: CommandRunner,
        usage: Usage,
        events: AttemptEvents | None = None,
        after_write: Callable[[Path], None] | None = None,
    ) -> None:
        self.workspace, self.config, self.usage, self.events = workspace, config, usage, events
        self.after_write = after_write
        self.state = TurnState(finish_check=config.finish_check)
        self.finished = False
        self.entries: list[dict[str, Any]] = []
        self.lock = asyncio.Lock()
        self.builtin: dict[str, FunctionTool] = {
            t.name: t for t in build_tools(workspace, config.cli_tools, self.state, run_command)
        }
        self.remote: dict[str, MCPServerStdio] = {}
        self.catalog: list[dict[str, Any]] = [
            {"name": t.name, "description": t.description, "inputSchema": t.params_json_schema}
            for t in self.builtin.values()
        ]

    async def start(self, stack: AsyncExitStack) -> None:
        """Start the template's MCP servers and add their granted tools."""
        for entry in self.config.mcp:
            server = await stack.enter_async_context(
                MCPServerStdio(
                    params={"command": entry.command, "args": entry.args, "env": entry.env},
                    name=entry.name,
                    tool_filter=create_static_tool_filter(allowed_tool_names=entry.tools_allowed),
                    client_session_timeout_seconds=entry.timeout_s,
                    cache_tools_list=True,
                )
            )
            for tool in await server.list_tools():
                if tool.name in entry.tools_allowed and tool.name not in self.granted:
                    self.remote[tool.name] = server
                    self.catalog.append(
                        {
                            "name": tool.name,
                            "description": tool.description or "",
                            "inputSchema": tool.input_schema,
                        }
                    )

    @property
    def granted(self) -> set[str]:
        return set(self.builtin) | set(self.remote)

    def new_step(self) -> None:
        """A new model response: track its own tool failures (as `openai_agents`)."""
        self.state.failed_in_step.clear()

    async def route(self, headers: dict[str, str], body: bytes) -> Reply:
        try:
            params = json.loads(body)
            name, arguments = params["name"], params.get("arguments") or {}
        except (ValueError, KeyError, TypeError):
            return json_reply(400, {"text": "error: bad tool request", "is_error": True})
        text, error = await self.call(str(name), arguments)
        return json_reply(200, {"text": text, "is_error": error})

    async def call(self, name: str, arguments: Any) -> tuple[str, bool]:
        """Run one tool call. Returns the text for the model and whether the call
        itself failed (refused, or the tool raised)."""
        async with self.lock:
            number = len(self.entries) + 1
            entry: dict[str, Any] = {"sequence": number, "tool": name, "admitted": False}
            self.entries.append(entry)
            if self.finished or name not in self.granted or not isinstance(arguments, dict):
                reason = "the task already finished" if self.finished else "tool not granted"
                self.state.refused.append(name)
                TOOL_ERRORS.labels(template=self.config.template_ref, tool=name).inc()
                log.warning("refused tool call", extra={"fields": {"tool": name}})
                entry["outcome"] = "refused"
                self._emit("tool_call", name, number)  # every result has its call (F91)
                self._emit("tool_result", name, number, "refused")
                return f"refused: {reason}", True
            entry["admitted"] = True
            self.usage.tool_calls += 1
            TOOL_CALLS.labels(template=self.config.template_ref, tool=name).inc()
            self._emit("tool_call", name, number)
            try:
                text, error = await self._run(name, arguments, number)
            except Exception as e:  # a tool error goes back to the model as text
                text, error = f"error: {type(e).__name__}: {e}"[:2000], True
            # A tool body reports its own errors as text, which the model reads as
            # it does with `openai_agents`; only a failed call is an MCP error.
            reported = looks_failed(text)
            failed = (error or reported) and name != FINISH_TOOL
            if failed:
                self.state.failed_in_step.append(name)
            if error or reported:
                TOOL_ERRORS.labels(template=self.config.template_ref, tool=name).inc()
            entry["outcome"] = "error" if failed else "ok"
            if name == STATUS_TOOL and not failed and self.events is not None:
                emit_agent_status(self.events, text)
            self._emit("tool_result", name, number, entry["outcome"])
            return text, error

    async def _run(self, name: str, arguments: dict[str, Any], number: int) -> tuple[str, bool]:
        tool = self.builtin.get(name)
        if tool is None:
            result = await asyncio.wait_for(
                self.remote[name].call_tool(name, arguments), MCP_CALL_TIMEOUT_S
            )
            parts = [getattr(item, "text", "") for item in result.content]
            return "".join(parts), bool(result.is_error)
        unknown = set(arguments) - set(tool.params_json_schema.get("properties", {}))
        if unknown:
            return f"error: unknown arguments: {', '.join(sorted(unknown))}", True
        text = await asyncio.to_thread(_invoke, tool, f"praxis-{number}", json.dumps(arguments))
        if name == FINISH_TOOL and self.state.finish is not None:
            self.finished = True
        if name == "write_file" and self.after_write is not None:
            self.after_write(self.workspace / str(arguments.get("path", "")))
        return text, False

    def _emit(self, kind: str, name: str, number: int, status: str | None = None) -> None:
        if self.events is None:
            return
        if kind == "tool_call":
            self.events.emit("tool_call", tool=name, call=number)
        else:
            self.events.emit("tool_result", tool=name, call=number, status=status)
