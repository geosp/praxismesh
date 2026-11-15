"""Trusted host executor for the R8 benchmark, using production tool semantics.

The model-facing catalog comes from harness_activity/tools.py and the real
sample-shop MCP server. File tools run the production wrappers against the
bind-mounted workspace. Shop tools run the real server in this host process, so
its database secret never enters the candidate. run_command applies the
production allowlist, then runs inside the owned candidate container.
"""

from __future__ import annotations

import asyncio
import json
import os
import shlex
import subprocess
import threading
from dataclasses import asdict
from pathlib import Path

import yaml
from agents import set_tracing_disabled
from agents.tool_context import ToolContext
from recovery_boundary import Refused
from run_probe import ROOT
from task_completion import InvalidCompletion

import sample_mcp.server as shop
from harness_activity.tools import COMMAND_TIMEOUT_S, OUTPUT_CAP, TurnState, build_tools

CLI_TOOLS = yaml.safe_load((ROOT / "registry/templates/local-default.yaml").read_text())[
    "cli_tools"
]
FILE_TOOLS = ("read_file", "write_file", "list_files")


class BenchTools:
    def __init__(self, workspace: Path, container: str, task_id: str, shop_tools: list[str]):
        set_tracing_disabled(True)
        self.workspace, self.container, self.task_id = workspace, container, task_id
        self.state = TurnState()
        # Production run_command is listed only for its schema; its body would run
        # on this host, so dispatch below executes inside the container instead.
        self.tools = {t.name: t for t in build_tools(workspace, CLI_TOOLS, self.state)}
        self.finished = threading.Event()
        self.lock = threading.Lock()
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever, daemon=True)
        self.thread.start()
        shop._engine = None  # bind the server's engine to this executor's loop
        listed = self.call(shop.server.list_tools())
        self.shop = [
            {"name": t.name, "description": t.description or "", "inputSchema": t.input_schema}
            for t in listed
            if t.name in shop_tools
        ]
        if {t["name"] for t in self.shop} != set(shop_tools):
            raise RuntimeError("blocked: sample-shop catalog differs from the template grant")

    def call(self, coroutine):
        return asyncio.run_coroutine_threadsafe(coroutine, self.loop).result(timeout=90)

    def catalog(self) -> list[dict]:
        return [
            {"name": t.name, "description": t.description, "inputSchema": t.params_json_schema}
            for t in self.tools.values()
        ] + self.shop

    def dispatch(self, name: str, arguments: dict) -> dict:
        with self.lock:
            if self.finished.is_set():
                raise Refused("completion already recorded")
            if name in self.tools:
                schema = self.tools[name].params_json_schema
                if set(arguments) - set(schema["properties"]):
                    raise InvalidCompletion("unknown tool fields")
            if name == "run_command":
                return {"result": self.run_command(arguments.get("command", ""))}
            if name in self.tools:
                payload = json.dumps(arguments)
                context = ToolContext(
                    context=None, tool_name=name, tool_call_id="bench", tool_arguments=payload
                )
                text = asyncio.run(self.tools[name].on_invoke_tool(context, payload))
                if name == "finish_task":
                    if self.state.finish is None:
                        raise InvalidCompletion(
                            "completion arguments failed existing tool validation"
                        )
                    self.finished.set()
                return {"result": text}
            if name not in {t["name"] for t in self.shop}:
                raise Refused("tool not granted")
            os.environ["PRAXIS_TASK_ID"] = self.task_id
            try:
                result = self.call(shop.server.call_tool(name, arguments))
            except Exception as error:
                # The production MCP client returns tool errors to the model as text.
                return {"error": f"{type(error).__name__}: {error}"}
            if result.is_error:
                return {"error": " ".join(getattr(c, "text", "") for c in result.content)}
            return {"result": result.structured_content or [c.text for c in result.content]}

    def run_command(self, command: str) -> str:
        allowed = ", ".join(CLI_TOOLS)
        try:
            first = shlex.split(command)[0] if command.strip() else ""
        except ValueError:
            first = ""
        if first not in CLI_TOOLS:
            self.state.refused.append(f"run_command:{first or '?'}")
            return f"refused: the command must start with one of: {allowed}"
        exec_command = [
            "docker",
            "exec",
            "--workdir",
            "/run/workspace",
            self.container,
            "env",
            "-i",
            "PATH=/usr/local/bin:/usr/bin:/bin",
            "HOME=/run/workspace",
            "LANG=C.UTF-8",
            "sh",
            "-c",
            command,
        ]
        try:
            done = subprocess.run(
                exec_command, capture_output=True, text=True, timeout=COMMAND_TIMEOUT_S
            )
        except subprocess.TimeoutExpired:
            return f"error: the command did not finish within {COMMAND_TIMEOUT_S} s"
        return (
            f"exit={done.returncode}\nstdout:\n{done.stdout[-OUTPUT_CAP:]}"
            f"\nstderr:\n{done.stderr[-OUTPUT_CAP // 2 :]}"
        )

    def report(self) -> dict | None:
        with self.lock:
            return asdict(self.state.finish) if self.state.finish is not None else None

    def close(self):
        engine = shop._engine
        if engine is not None:
            self.call(engine.dispose())
            shop._engine = None
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(timeout=5)
