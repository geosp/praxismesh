"""How should a harness turn end? `output_type` against a `finish_task` tool.

    uv run finish_tool_check.py .env

Runs a tiny agent three times each way against VLLM_BASE_URL (from the given
.env), with one price-lookup tool. Result on 2026-11-11 (vLLM 0.32.0, served
model `spark` = qwen3.8-flash-next, openai-agents 0.24.0): `output_type` 0 of 3
(every run hit MaxTurnsExceeded: with a JSON-schema response_format the model
never finished), `finish_task` 3 of 3. Recorded in docs/roadmap/decision-log.md
and docs/rfcs/phase-1-single-agent.md.
"""

import asyncio
import os
import sys
from typing import Literal

from agents import (
    Agent,
    OpenAIChatCompletionsModel,
    Runner,
    function_tool,
    set_trace_processors,
    set_tracing_disabled,
)
from agents.items import ToolCallItem
from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic import BaseModel


class FinalReport(BaseModel):
    status: Literal["done", "needs_input"]
    summary: str


@function_tool
def lookup_price(sku: str) -> float:
    """Return the unit price in USD for a product SKU such as SKU-1."""
    return {"SKU-1": 12.5, "SKU-2": 7.25}.get(sku, 0.0)


@function_tool
def finish_task(status: Literal["done", "needs_input"], summary: str) -> str:
    """Call exactly once when the task is complete, or when you need input from the user."""
    return "recorded"


async def main() -> None:
    load_dotenv(sys.argv[1])
    set_tracing_disabled(True)
    set_trace_processors([])
    base = os.environ["VLLM_BASE_URL"].rstrip("/")
    model = OpenAIChatCompletionsModel(
        model="spark", openai_client=AsyncOpenAI(base_url=f"{base}/v1", api_key="local")
    )
    prompt = "What is the total price of 3 units of SKU-1 and 2 units of SKU-2? Use the tool."
    for mode in ("output_type", "finish_tool"):
        for run in range(3):
            if mode == "output_type":
                agent = Agent(
                    name="t", instructions="Use tools, then report.", model=model,
                    tools=[lookup_price], output_type=FinalReport,
                )
            else:
                agent = Agent(
                    name="t", instructions="Use tools, then call finish_task.", model=model,
                    tools=[lookup_price, finish_task],
                    tool_use_behavior={"stop_at_tool_names": ["finish_task"]},
                )
            try:
                result = await Runner.run(agent, prompt, max_turns=8)
                calls = [
                    getattr(i.raw_item, "name", "?")
                    for i in result.new_items
                    if isinstance(i, ToolCallItem)
                ]
                print(f"{mode} run{run}: tools={calls} final={str(result.final_output)[:100]!r}")
            except Exception as e:
                print(f"{mode} run{run}: ERROR {type(e).__name__}: {str(e)[:160]}")


asyncio.run(main())
