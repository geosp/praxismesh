"""Built-in tools for a harness turn (RFC Phase 1: run_harness_turn, command tool).

File tools stay inside the workspace. `run_command` is offered only when the
template lists `cli_tools`; the command's first word must be one of them, and it
runs in the workspace with a minimal, credential-free environment, a timeout and
capped output. This is not a sandbox for untrusted code (Phase 5).

`finish_task` ends the run: the runner stops on it and reads the validated
arguments recorded here, because the SDK also stops on a call with invalid
arguments and then returns only an error string (design review J11).
"""

from __future__ import annotations

import logging
import os
import shlex
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from agents import FunctionTool, function_tool

from harness_activity.skills import SKILLS_DIR

log = logging.getLogger("praxis.harness")
COMMAND_TIMEOUT_S = 60
OUTPUT_CAP = 8000
FINISH_TOOL = "finish_task"


@dataclass
class FinishReport:
    status: Literal["done", "needs_input"]
    summary: str
    questions: list[str] = field(default_factory=list)


@dataclass
class TurnState:
    """Per-run state the tools write and the runner reads."""

    finish: FinishReport | None = None
    refused: list[str] = field(default_factory=list)
    failed_in_step: list[str] = field(default_factory=list)


class WorkspaceError(ValueError):
    pass


def inside(workspace: Path, path: str) -> Path:
    resolved = (workspace / path).resolve()
    root = workspace.resolve()
    if resolved != root and root not in resolved.parents:
        raise WorkspaceError(f"path outside the workspace: {path}")
    return resolved


def command_env(workspace: Path) -> dict[str, str]:
    """The only environment a command sees: no credentials, no template secrets."""
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(workspace),
        "LANG": "C.UTF-8",
    }


def build_tools(workspace: Path, cli_tools: list[str], state: TurnState) -> list[FunctionTool]:
    # File tools return their errors as text: the SDK would otherwise replace an
    # exception with a generic message, and the model could not tell why it failed.
    @function_tool
    def read_file(path: str) -> str:
        """Return the text content of a file in the project directory."""
        try:
            return inside(workspace, path).read_text()
        except (WorkspaceError, OSError, UnicodeDecodeError) as e:
            return f"error: {e}"

    @function_tool
    def write_file(path: str, content: str) -> str:
        """Create or overwrite a file in the project directory with the given text."""
        try:
            target = inside(workspace, path)
            if target.relative_to(workspace.resolve()).parts[:1] == (SKILLS_DIR,):
                raise WorkspaceError("skills are read-only")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
        except (WorkspaceError, OSError) as e:
            return f"error: {e}"
        return f"wrote {len(content)} characters to {path}"

    @function_tool
    def list_files(path: str = ".") -> list[str] | str:
        """List the files under a directory of the project, recursively."""
        try:
            base = inside(workspace, path)
        except WorkspaceError as e:
            return f"error: {e}"
        root = workspace.resolve()
        return sorted(
            str(p.relative_to(root)) for p in base.rglob("*") if p.is_file() and not p.is_symlink()
        )

    @function_tool
    def finish_task(
        status: Literal["done", "needs_input"], summary: str, questions: list[str] | None = None
    ) -> str:
        """Call exactly once: when the task is complete (status "done"), or when you
        cannot continue without information from the user (status "needs_input",
        with your questions)."""
        state.finish = FinishReport(status, summary[:2000], list(questions or []))
        return "recorded"

    tools: list[FunctionTool] = [read_file, write_file, list_files, finish_task]
    if cli_tools:
        allowed = ", ".join(cli_tools)

        @function_tool(
            name_override="run_command",
            description_override=(
                "Run a shell command in the project directory and return its exit code and "
                f"output. The command must start with one of: {allowed}."
            ),
        )
        def run_command(command: str) -> str:
            try:
                first = shlex.split(command)[0] if command.strip() else ""
            except ValueError:
                first = ""
            if first not in cli_tools:
                state.refused.append(f"run_command:{first or '?'}")
                log.warning("refused command", extra={"fields": {"program": first or "?"}})
                return f"refused: the command must start with one of: {allowed}"
            try:
                done = subprocess.run(
                    ["sh", "-c", command],
                    cwd=workspace,
                    env=command_env(workspace),
                    capture_output=True,
                    text=True,
                    timeout=COMMAND_TIMEOUT_S,
                )
            except subprocess.TimeoutExpired:
                return f"error: the command did not finish within {COMMAND_TIMEOUT_S} s"
            return (
                f"exit={done.returncode}\nstdout:\n{done.stdout[-OUTPUT_CAP:]}"
                f"\nstderr:\n{done.stderr[-OUTPUT_CAP // 2 :]}"
            )

        tools.append(run_command)
    return tools


def tool_names(tools: list[Any]) -> set[str]:
    return {t.name for t in tools}
