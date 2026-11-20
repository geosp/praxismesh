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

import contextlib
import errno
import logging
import os
import shlex
import stat
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from agents import FunctionTool, function_tool

from harness_activity.skills import SKILLS_DIR

log = logging.getLogger("praxis.harness")
COMMAND_TIMEOUT_S = 60
OUTPUT_CAP = 8000
FINISH_TOOL = "finish_task"


@dataclass
class FinishReport:
    status: Literal["done", "needs_input", "waiting"]
    summary: str
    questions: list[str] = field(default_factory=list)


@dataclass
class TurnState:
    """Per-run state the tools write and the runner reads."""

    finish: FinishReport | None = None
    # Why the task may not finish yet; from HarnessConfig.finish_check.
    finish_check: Callable[[], list[str]] | None = None
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


def _parts(workspace: Path, path: str) -> list[str]:
    """The components of `path` below the workspace; no `..`, nothing outside."""
    pure = PurePosixPath(path)
    if pure.is_absolute():
        try:
            pure = pure.relative_to(PurePosixPath(workspace.resolve()))
        except ValueError:
            raise WorkspaceError(f"path outside the workspace: {path}") from None
    parts = [p for p in pure.parts if p != "."]
    if ".." in parts:
        raise WorkspaceError(f"path outside the workspace: {path}")
    return parts


def open_inside(
    workspace: Path, path: str, flags: int, mode: int = 0o664, *, make_dirs: bool = False
) -> int:
    """Open `path` in the workspace without following any symbolic link: every
    component is opened relative to its parent with O_NOFOLLOW. Another UID can
    write the workspace (a DSH command), so a link, even one swapped in after a
    check, must never take the worker out of it (DSH plan D4, review F97)."""
    parts = _parts(workspace, path)
    if not parts:
        raise WorkspaceError(f"not a file in the workspace: {path}")
    directory = os.open(workspace, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for name in parts[:-1]:
            if make_dirs:
                with contextlib.suppress(FileExistsError):
                    os.mkdir(name, 0o770, dir_fd=directory)
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = child
        return os.open(parts[-1], flags | os.O_NOFOLLOW | os.O_NONBLOCK, mode, dir_fd=directory)
    except OSError as error:
        if error.errno in (errno.ELOOP, errno.ENOTDIR):
            raise WorkspaceError(f"path outside the workspace: {path}") from None
        raise
    finally:
        os.close(directory)


def read_regular(workspace: Path, path: str) -> bytes:
    """The bytes of a regular file in the workspace, never through a link."""
    fd = open_inside(workspace, path, os.O_RDONLY)
    with os.fdopen(fd, "rb") as f:
        if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):
            raise WorkspaceError(f"not a regular file: {path}")
        return f.read()


def command_env(workspace: Path) -> dict[str, str]:
    """The only environment a command sees: no credentials, no template secrets."""
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(workspace),
        "LANG": "C.UTF-8",
    }


@dataclass(frozen=True)
class CommandResult:
    exit: int | None
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False


CommandRunner = Callable[[str], CommandResult]


def local_command_runner(workspace: Path) -> CommandRunner:
    """Run a command with `sh -c` in the workspace, as openai_agents does."""

    def run(command: str) -> CommandResult:
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
            return CommandResult(None, timed_out=True)
        return CommandResult(done.returncode, done.stdout, done.stderr)

    return run


# Tool bodies, shared by every runner (DSH migration plan D4). The openai_agents
# wrappers below and the DSH executor call these, so both runners present the same
# semantics; only where a command runs differs (the CommandRunner).


def read_file_body(workspace: Path, path: str) -> str:
    try:
        return read_regular(workspace, path).decode()
    except (WorkspaceError, OSError, UnicodeDecodeError) as e:
        return f"error: {e}"


def write_file_body(workspace: Path, path: str, content: str) -> str:
    try:
        if _parts(workspace, path)[:1] == [SKILLS_DIR]:
            raise WorkspaceError("skills are read-only")
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        fd = open_inside(workspace, path, flags, make_dirs=True)
        with os.fdopen(fd, "w") as f:
            if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):
                raise WorkspaceError(f"not a regular file: {path}")
            f.write(content)
    except (WorkspaceError, OSError) as e:
        return f"error: {e}"
    return f"wrote {len(content)} characters to {path}"


def list_files_body(workspace: Path, path: str = ".") -> list[str] | str:
    try:
        parts = _parts(workspace, path)
        top = (
            open_inside(workspace, path, os.O_RDONLY | os.O_DIRECTORY)
            if parts
            else os.open(workspace, os.O_RDONLY | os.O_DIRECTORY)
        )
    except (WorkspaceError, OSError) as e:
        return f"error: {e}"
    # Walk by descriptor, never following a link, so nothing swapped in after the
    # open takes the listing outside the workspace (review F140).
    found = []
    try:
        for directory, _, files, fd in os.fwalk(".", dir_fd=top, follow_symlinks=False):
            for name in files:
                info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                if stat.S_ISREG(info.st_mode):
                    found.append(str(PurePosixPath(*parts, directory, name)))
    finally:
        os.close(top)
    return sorted(os.path.normpath(p) for p in found)


QUESTIONS_MAX = 20
QUESTION_MAX_CHARS = 500


def bounded_questions(questions: list[str] | None) -> list[str]:
    """The first 20 questions, each cut to 500 characters (D9)."""
    return [q[:QUESTION_MAX_CHARS] for q in (questions or [])[:QUESTIONS_MAX]]


def finish_task_body(
    state: TurnState,
    status: Literal["done", "needs_input", "waiting"],
    summary: str,
    questions: list[str] | None = None,
) -> str:
    if status != "waiting" and state.finish_check is not None:
        blocking = state.finish_check()
        if blocking:  # R19: the run goes on, so the model can wait instead
            return (
                "refused: you cannot finish while " + "; ".join(blocking) + ". Call finish_task "
                'with status "waiting" to be woken with the answers.'
            )
    # Bounded like the summary, so a turn's outcome stays small in Workflow
    # history (Phase 3A persistence plan D9); the schemas stay permissive.
    state.finish = FinishReport(status, summary[:2000], bounded_questions(questions))
    return "recorded"


def run_command_body(
    state: TurnState, cli_tools: list[str], command: str, runner: CommandRunner
) -> str:
    allowed = ", ".join(cli_tools)
    try:
        first = shlex.split(command)[0] if command.strip() else ""
    except ValueError:
        first = ""
    if first not in cli_tools:
        state.refused.append(f"run_command:{first or '?'}")
        log.warning("refused command", extra={"fields": {"program": first or "?"}})
        return f"refused: the command must start with one of: {allowed}"
    done = runner(command)
    if done.timed_out:
        return f"error: the command did not finish within {COMMAND_TIMEOUT_S} s"
    return (
        f"exit={done.exit}\nstdout:\n{done.stdout[-OUTPUT_CAP:]}"
        f"\nstderr:\n{done.stderr[-OUTPUT_CAP // 2 :]}"
    )


def run_command_description(cli_tools: list[str]) -> str:
    return (
        "Run a shell command in the project directory and return its exit code and "
        f"output. The command must start with one of: {', '.join(cli_tools)}."
    )


def build_tools(
    workspace: Path,
    cli_tools: list[str],
    state: TurnState,
    runner: CommandRunner | None = None,
) -> list[FunctionTool]:
    # File tools return their errors as text: the SDK would otherwise replace an
    # exception with a generic message, and the model could not tell why it failed.
    run = runner or local_command_runner(workspace)

    @function_tool
    def read_file(path: str) -> str:
        """Return the text content of a file in the project directory."""
        return read_file_body(workspace, path)

    @function_tool
    def write_file(path: str, content: str) -> str:
        """Create or overwrite a file in the project directory with the given text."""
        return write_file_body(workspace, path, content)

    @function_tool
    def list_files(path: str = ".") -> list[str] | str:
        """List the files under a directory of the project, recursively."""
        return list_files_body(workspace, path)

    @function_tool
    def finish_task(
        status: Literal["done", "needs_input", "waiting"],
        summary: str,
        questions: list[str] | None = None,
    ) -> str:
        """Call exactly once: when the task is complete (status "done"), when you
        cannot continue without information from the user (status "needs_input",
        with your questions), or when you are waiting for another task's message or
        answer (status "waiting"); a waiting task is woken when one arrives."""
        return finish_task_body(state, status, summary, questions)

    tools: list[FunctionTool] = [read_file, write_file, list_files, finish_task]
    if cli_tools:

        @function_tool(
            name_override="run_command", description_override=run_command_description(cli_tools)
        )
        def run_command(command: str) -> str:
            return run_command_body(state, cli_tools, command, run)

        tools.append(run_command)
    return tools


def tool_names(tools: list[Any]) -> set[str]:
    return {t.name for t in tools}
