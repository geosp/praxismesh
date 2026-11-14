# Pre-0.1 spike: Claude harness on a local model via vLLM

Throwaway experiment for [docs/roadmap/bootstrap.md](../../docs/roadmap/bootstrap.md) Pre-0.1 (issue #31). Not product code: it has its own `uv` project and is excluded from the root lint and type checks.

**Question:** can a Claude harness (Claude Agent SDK) complete multi-step, tool-using work against `qwen3.8-flash-next` served by vLLM's Anthropic Messages endpoint? The OpenAI Agents SDK on vLLM's OpenAI-compatible endpoint runs the same tasks as the fallback.

**Threshold (set by the owner before the run, 2026-11-11):** go if at least 7 of 10 tasks succeed with no manual help.

## Files

| File | Purpose |
|---|---|
| `shop_server.py` | Stdio MCP server with shop data (`get_price`, `get_stock`, `get_discount`, `get_setting`); both harnesses use it |
| `tasks.py` | Ten tasks; each needs an MCP call, a shell command and a file edit, and has a deterministic checker |
| `run_claude.py` | Claude Agent SDK runner (isolated config dir, no user or project settings, dummy key) |
| `run_openai.py` | OpenAI Agents SDK runner (own file and shell tools, same MCP server) |
| `results/*.jsonl` | One record per task: pass or fail, turns, tool calls, MCP calls, tool errors, stalls, tokens, seconds |

## Run

The agents get a shell in a temporary directory per task, without confirmation prompts, so run them yourself on a machine where that is acceptable.

```bash
cd spikes/harness-vllm
printf 'VLLM_BASE_URL=http://<spark-host>:8000\n' > .env    # git-ignored
env -u VIRTUAL_ENV uv sync
env -u VIRTUAL_ENV uv run run_claude.py          # all 10 tasks; or name task ids
env -u VIRTUAL_ENV uv run run_openai.py
```

`env -u VIRTUAL_ENV` keeps `uv` from using the repository root's virtual environment.
