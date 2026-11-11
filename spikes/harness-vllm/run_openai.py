"""Run the task set with the OpenAI Agents SDK against vLLM's OpenAI endpoint.

    uv run run_openai.py [task-id ...]

Fallback harness for Pre-0.1. It gets its own file and shell tools (the SDK has
no built-in ones) and the same stdio MCP shop server as the Claude harness.
The endpoint comes from VLLM_BASE_URL in the git-ignored .env file.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from agents import Agent, OpenAIChatCompletionsModel, Runner, function_tool, set_tracing_disabled
from agents.exceptions import MaxTurnsExceeded
from agents.items import ToolCallItem, ToolCallOutputItem
from agents.mcp import MCPServerStdio
from dotenv import load_dotenv
from openai import AsyncOpenAI

from tasks import TASKS, setup

HERE = Path(__file__).resolve().parent
MODEL = "spark"
MAX_TURNS = 30
TIMEOUT_S = 900
BLOCKED = ("sudo ", "rm -rf /", "rm -rf ~", "curl ", "wget ")

INSTRUCTIONS = (
    "You are a coding agent working in a project directory. Use the tools to read and write "
    "files, run shell commands in the project directory, and query the shop MCP tools. "
    "Complete the task fully, verify your result, then reply with a one-line summary."
)


def make_tools(work: Path):
    def inside(path: str) -> Path:
        p = (work / path).resolve()
        if work.resolve() not in (p, *p.parents):
            raise ValueError("path outside the project directory")
        return p

    @function_tool
    def read_file(path: str) -> str:
        """Return the text content of a file in the project directory."""
        return inside(path).read_text()

    @function_tool
    def write_file(path: str, content: str) -> str:
        """Create or overwrite a file in the project directory with the given text."""
        p = inside(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return f"wrote {len(content)} bytes to {path}"

    @function_tool
    def run_shell(command: str) -> str:
        """Run a shell command in the project directory and return exit code, stdout, stderr."""
        if any(b in command for b in BLOCKED):
            return "refused: command not allowed in this spike"
        r = subprocess.run(command, shell=True, cwd=work, capture_output=True, text=True, timeout=60)
        return f"exit={r.returncode}\nstdout:\n{r.stdout[-4000:]}\nstderr:\n{r.stderr[-2000:]}"

    return [read_file, write_file, run_shell]


async def run_task(task, work: Path, client: AsyncOpenAI) -> dict:
    setup(task, work)
    rec: dict = {"task": task.id, "harness": "openai-agents", "tool_calls": 0, "tool_errors": 0,
                 "tools_used": {}, "mcp_calls": 0}
    t0 = time.monotonic()
    shop = MCPServerStdio(
        params={"command": sys.executable, "args": [str(HERE / "shop_server.py")]},
        name="shop", client_session_timeout_seconds=30,
    )
    try:
        async with shop:
            agent = Agent(
                name="spike", instructions=INSTRUCTIONS, tools=make_tools(work), mcp_servers=[shop],
                model=OpenAIChatCompletionsModel(model=MODEL, openai_client=client),
            )
            result = await asyncio.wait_for(
                Runner.run(agent, task.prompt, max_turns=MAX_TURNS), timeout=TIMEOUT_S
            )
        mcp_names = {"get_price", "get_stock", "get_discount", "get_setting"}
        for item in result.new_items:
            if isinstance(item, ToolCallItem):
                name = getattr(item.raw_item, "name", "?")
                rec["tool_calls"] += 1
                rec["tools_used"][name] = rec["tools_used"].get(name, 0) + 1
                rec["mcp_calls"] += name in mcp_names
            elif isinstance(item, ToolCallOutputItem) and "error" in str(item.output).lower()[:80]:
                rec["tool_errors"] += 1
        u = result.context_wrapper.usage
        rec.update(subtype="success", stalled=False, turns=len(result.raw_responses),
                   usage={"input_tokens": u.input_tokens, "output_tokens": u.output_tokens},
                   final=str(result.final_output)[:300])
    except MaxTurnsExceeded:
        rec.update(subtype="error_max_turns", stalled=True)
    except TimeoutError:
        rec.update(subtype="timeout", stalled=True)
    except Exception as e:  # harness crash counts as a failure, recorded verbatim
        rec.update(subtype="harness_error", stalled=False, error=f"{type(e).__name__}: {e}"[:500])
    rec["seconds"] = round(time.monotonic() - t0, 1)
    rec["passed"], rec["check"] = task.check(work)
    return rec


async def main(selected: list[str]) -> None:
    load_dotenv(HERE / ".env")
    set_tracing_disabled(True)
    client = AsyncOpenAI(base_url=os.environ["VLLM_BASE_URL"].rstrip("/") + "/v1", api_key="spike-local-dummy")
    out = HERE / "results" / "openai-agents.jsonl"
    out.parent.mkdir(exist_ok=True)
    tasks = [t for t in TASKS if not selected or t.id in selected]
    with tempfile.TemporaryDirectory() as tmp, out.open("a") as f:
        for task in tasks:
            rec = await run_task(task, Path(tmp) / task.id, client)
            rec["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            f.write(json.dumps(rec) + "\n")
            f.flush()
            print(f"{task.id:20} {'PASS' if rec['passed'] else 'FAIL'}  turns={rec.get('turns')} "
                  f"tools={rec['tool_calls']} mcp={rec['mcp_calls']} err={rec['tool_errors']} "
                  f"{rec.get('subtype')} {rec['seconds']}s  {rec['check']}", flush=True)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
