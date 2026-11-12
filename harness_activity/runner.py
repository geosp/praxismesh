"""`HarnessRunner`: the interface `run_harness_turn` calls, and the openai-agents
runner (RFC Phase 1: HarnessRunner; owner decision: openai_agents only in Phase 1).

Contract for any runner: configuration only from the template; hooks for
checkpoints and heartbeats; cumulative usage; the run ends through `finish_task`.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from contextlib import AsyncExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

from agents import (
    Agent,
    MaxTurnsExceeded,
    ModelBehaviorError,
    OpenAIChatCompletionsModel,
    RunConfig,
    RunContextWrapper,
    RunHooks,
    Runner,
    Tool,
)
from agents.mcp import MCPServerStdio, create_static_tool_filter
from agents.memory import Session
from openai import AsyncOpenAI
from opentelemetry import trace
from opentelemetry.trace import Span, Tracer

from common.observability.metrics import TOOL_CALLS, TOOL_ERRORS
from harness_activity import skills
from harness_activity.config import HarnessConfig
from harness_activity.tools import FINISH_TOOL, TurnState, build_tools

log = logging.getLogger("praxis.harness")


@dataclass
class Usage:
    tokens_in: int = 0
    tokens_out: int = 0
    tool_calls: int = 0
    inner_turns: int = 0


@dataclass
class RunResult:
    status: Literal["done", "continue", "needs_input"]
    usage: Usage
    summary: str = ""
    questions: list[str] | None = None
    error: str | None = None


class StopRun(Exception):
    """Raised by `before_model_call` to end the run early because the task's token
    budget is used up. The turn then returns `continue`."""


class Superseded(Exception):
    """Raised by `before_model_call` when a newer attempt of the same turn exists.
    The runner lets it propagate: a superseded attempt writes nothing more."""


# Called at the start of every inner turn, before the model call (RFC: the
# checkpoint hook point). It may raise `StopRun`.
BeforeModelCall = Callable[[Usage], Awaitable[None]]


class HarnessRunner(Protocol):
    async def run(
        self,
        config: HarnessConfig,
        workspace: Path,
        session: Session,
        input_text: str,
        before_model_call: BeforeModelCall,
        usage: Usage,
    ) -> RunResult:
        """Run once. `usage` is updated live, so the caller can heartbeat it."""
        ...


def _looks_failed(result: str) -> bool:
    """Tool errors the SDK or our tools return as text."""
    head = result.lstrip()[:80].lower()
    return head.startswith(("an error occurred", "error", "refused"))


class _Hooks(RunHooks[Any]):
    """Counts usage, logs refusals, and adds trace spans for model and tool calls
    under the Activity's span (RFC: Observability baseline)."""

    def __init__(
        self,
        usage: Usage,
        allowed: set[str],
        state: TurnState,
        before: BeforeModelCall,
        tracer: Tracer,
        template: str,
    ) -> None:
        self.usage, self.allowed, self.state, self.before = usage, allowed, state, before
        self.tracer = tracer
        self.template = template
        self.model_span: Span | None = None
        self.tool_spans: dict[str, Span] = {}

    async def on_llm_start(
        self, context: Any, agent: Any, system_prompt: Any, input_items: Any
    ) -> None:
        await self.before(self.usage)
        self.usage.inner_turns += 1
        self.model_span = self.tracer.start_span(
            "model call", attributes={"praxis.inner_turn": self.usage.inner_turns}
        )

    async def on_llm_end(self, context: RunContextWrapper[Any], agent: Any, response: Any) -> None:
        self.state.failed_in_step.clear()  # a new step: track its own tool failures
        self.usage.tokens_in += response.usage.input_tokens
        self.usage.tokens_out += response.usage.output_tokens
        if self.model_span is not None:
            self.model_span.set_attribute("praxis.tokens_in", response.usage.input_tokens)
            self.model_span.set_attribute("praxis.tokens_out", response.usage.output_tokens)
            self.model_span.end()
            self.model_span = None
        for item in response.output:
            name = getattr(item, "name", None)
            if getattr(item, "type", None) == "function_call" and name not in self.allowed:
                # No hook fires for a tool that does not exist, so refusals are
                # logged here; the SDK returns the error to the model.
                self.state.refused.append(str(name))
                TOOL_ERRORS.labels(template=self.template, tool=str(name)).inc()
                log.warning("refused tool call", extra={"fields": {"tool": name}})

    async def on_tool_start(self, context: Any, agent: Any, tool: Tool) -> None:
        self.usage.tool_calls += 1
        TOOL_CALLS.labels(template=self.template, tool=tool.name).inc()
        self.tool_spans[tool.name] = self.tracer.start_span(
            "tool call", attributes={"praxis.tool": tool.name}
        )

    async def on_tool_end(self, context: Any, agent: Any, tool: Tool, result: object) -> None:
        failed = tool.name != FINISH_TOOL and _looks_failed(str(result))
        if failed:
            self.state.failed_in_step.append(tool.name)
        if failed or _looks_failed(str(result)):
            TOOL_ERRORS.labels(template=self.template, tool=tool.name).inc()
        span = self.tool_spans.pop(tool.name, None)
        if span is not None:
            span.set_attribute("praxis.tool_failed", failed)
            span.end()


class OpenAIAgentsRunner:
    def __init__(self, tracer: Tracer | None = None) -> None:
        self.tracer = tracer or trace.get_tracer("praxismesh.harness")

    async def run(
        self,
        config: HarnessConfig,
        workspace: Path,
        session: Session,
        input_text: str,
        before_model_call: BeforeModelCall,
        usage: Usage,
    ) -> RunResult:
        state = TurnState()
        instructions = config.instructions
        if config.skills_bundle is not None:
            mounted = skills.mount(config.skills_bundle, workspace)
            instructions += "\n\n" + skills.index(config.skills_bundle, mounted, workspace)
        tools = build_tools(workspace, config.cli_tools, state)
        allowed = {t.name for t in tools} | {n for s in config.mcp for n in s.tools_allowed}
        client = AsyncOpenAI(base_url=f"{config.base_url}/v1", api_key=config.api_key)
        async with AsyncExitStack() as stack:
            servers = [
                await stack.enter_async_context(
                    MCPServerStdio(
                        params={"command": s.command, "args": s.args, "env": s.env},
                        name=s.name,
                        tool_filter=create_static_tool_filter(allowed_tool_names=s.tools_allowed),
                        client_session_timeout_seconds=s.timeout_s,
                        cache_tools_list=True,
                    )
                )
                for s in config.mcp
            ]
            agent = Agent(
                name="praxis",
                instructions=instructions,
                model=OpenAIChatCompletionsModel(model=config.model, openai_client=client),
                tools=list(tools),
                mcp_servers=list(servers),
                tool_use_behavior={"stop_at_tool_names": [FINISH_TOOL]},
            )
            try:
                await Runner.run(
                    agent,
                    input_text,
                    max_turns=config.inner_max_turns,
                    session=session,
                    hooks=_Hooks(
                        usage, allowed, state, before_model_call, self.tracer, config.template_ref
                    ),
                    run_config=RunConfig(
                        tracing_disabled=True, tool_not_found_behavior="return_error_to_model"
                    ),
                )
            except MaxTurnsExceeded:
                return RunResult("continue", usage, summary="inner-turn limit reached")
            except StopRun as e:  # Superseded is not caught: it propagates
                return RunResult("continue", usage, summary=str(e))
            except ModelBehaviorError as e:
                # A model mistake, not an infrastructure failure: the next harness
                # turn resumes from the last checkpoint (RFC: model mistakes).
                return RunResult("continue", usage, error=f"model behavior: {e}"[:500])
        if state.finish is None:
            return RunResult("continue", usage, summary="stopped without finish_task")
        if state.failed_in_step:
            # finish_task came with another call that failed; the model never saw
            # that result, so the turn is not done (design review J12).
            failed = ", ".join(state.failed_in_step)
            return RunResult("continue", usage, summary=f"finish_task alongside failed: {failed}")
        return RunResult(
            state.finish.status,
            usage,
            summary=state.finish.summary,
            questions=state.finish.questions,
        )
