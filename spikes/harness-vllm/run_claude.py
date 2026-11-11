"""Run the task set with the Claude Agent SDK against vLLM's Anthropic endpoint.

    uv run run_claude.py [task-id ...]

Isolation: a temporary CLAUDE_CONFIG_DIR (no user credentials or settings),
setting_sources=[] (no user/project/local settings), a dummy API key, every
model alias mapped to the served model, and only the tools the tasks need.
The endpoint comes from VLLM_BASE_URL in the git-ignored .env file.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path

from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ResultMessage, UserMessage, query
from dotenv import load_dotenv

from tasks import TASKS, setup

HERE = Path(__file__).resolve().parent
MODEL = "spark"
MAX_TURNS = 30
# The served Qwen template accepts reasoning effort low|medium|xhigh, not "high"
# (Claude Code's default); "low" is the model's server default in the registry.
EFFORT = "low"
TIMEOUT_S = 900
SHOP_TOOLS = [f"mcp__shop__{t}" for t in ("get_price", "get_stock", "get_discount", "get_setting")]
GUARD = ["Bash(sudo *)", "Bash(rm -rf /*)", "Bash(rm -rf ~*)", "Bash(curl *)", "Bash(wget *)"]


def block_type(block: object) -> str:
    return type(block).__name__


async def run_task(task, work: Path, config_dir: Path) -> dict:
    setup(task, work)
    env = {
        "ANTHROPIC_BASE_URL": os.environ["VLLM_BASE_URL"],
        "ANTHROPIC_API_KEY": "spike-local-dummy",
        "ANTHROPIC_MODEL": MODEL,
        "ANTHROPIC_DEFAULT_OPUS_MODEL": MODEL,
        "ANTHROPIC_DEFAULT_SONNET_MODEL": MODEL,
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": MODEL,
        "ANTHROPIC_SMALL_FAST_MODEL": MODEL,
        "CLAUDE_CONFIG_DIR": str(config_dir),
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        "DISABLE_TELEMETRY": "1",
        "CLAUDE_CODE_EFFORT_LEVEL": EFFORT,
        "CLAUDE_CODE_SUBAGENT_EFFORT": EFFORT,
    }
    options = ClaudeAgentOptions(
        cwd=str(work),
        model=MODEL,
        max_turns=MAX_TURNS,
        effort=EFFORT,
        setting_sources=[],
        system_prompt={"type": "preset", "preset": "claude_code"},
        permission_mode="dontAsk",
        allowed_tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep", *SHOP_TOOLS],
        disallowed_tools=["WebFetch", "WebSearch", "Task", *GUARD],
        mcp_servers={
            "shop": {"type": "stdio", "command": sys.executable, "args": [str(HERE / "shop_server.py")]}
        },
        env=env,
    )
    rec: dict = {"task": task.id, "harness": "claude-agent-sdk", "tool_calls": 0, "tool_errors": 0,
                 "tools_used": {}, "mcp_calls": 0}
    t0 = time.monotonic()

    async def consume() -> None:
        async for msg in query(prompt=task.prompt, options=options):
            if isinstance(msg, AssistantMessage):
                for b in msg.content:
                    if block_type(b) == "ToolUseBlock":
                        rec["tool_calls"] += 1
                        name = getattr(b, "name", "?")
                        rec["tools_used"][name] = rec["tools_used"].get(name, 0) + 1
                        rec["mcp_calls"] += name.startswith("mcp__shop__")
            elif isinstance(msg, UserMessage) and isinstance(msg.content, list):
                for b in msg.content:
                    if block_type(b) == "ToolResultBlock" and getattr(b, "is_error", False):
                        rec["tool_errors"] += 1
            elif isinstance(msg, ResultMessage):
                rec.update(subtype=msg.subtype, is_error=msg.is_error, turns=msg.num_turns,
                           usage=msg.usage, final=(msg.result or "")[:300])

    try:
        await asyncio.wait_for(consume(), timeout=TIMEOUT_S)
        rec["stalled"] = rec.get("subtype") == "error_max_turns"
    except TimeoutError:
        rec.update(stalled=True, subtype="timeout")
    except Exception as e:  # harness crash counts as a failure, recorded verbatim
        rec.update(stalled=False, subtype="harness_error", error=f"{type(e).__name__}: {e}"[:500])
    rec["seconds"] = round(time.monotonic() - t0, 1)
    rec["passed"], rec["check"] = task.check(work)
    return rec


async def main(selected: list[str]) -> None:
    load_dotenv(HERE / ".env")
    out = HERE / "results" / "claude-agent-sdk.jsonl"
    out.parent.mkdir(exist_ok=True)
    tasks = [t for t in TASKS if not selected or t.id in selected]
    with tempfile.TemporaryDirectory() as tmp, out.open("a") as f:
        for task in tasks:
            rec = await run_task(task, Path(tmp) / task.id, Path(tmp) / "claude-config")
            rec["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            f.write(json.dumps(rec) + "\n")
            f.flush()
            print(f"{task.id:20} {'PASS' if rec['passed'] else 'FAIL'}  turns={rec.get('turns')} "
                  f"tools={rec['tool_calls']} mcp={rec['mcp_calls']} err={rec['tool_errors']} "
                  f"{rec.get('subtype')} {rec['seconds']}s  {rec['check']}", flush=True)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
