# Spike: Claude harness on a local model via vLLM (Pre-0.1)

**Date:** 2026-11-11. **Issue:** #31. **Code and raw results:** [spikes/harness-vllm/](../../spikes/harness-vllm/).

**Decision: go.** The Claude harness on vLLM's Anthropic Messages endpoint is the primary path. It needs one required configuration (reasoning effort pinned to a value the model accepts; see Findings), and its input-token cost is about 14 times the fallback's. The OpenAI-agents harness passed the same tasks and stays a measured, viable fallback.

## Question and threshold

Can a Claude harness complete multi-step, tool-using work against a local model served by vLLM's Anthropic Messages-compatible endpoint, reliably enough to build on? (Plan Pre-0.1.)

The threshold was set by the owner before the run: **go if at least 7 of 10 tasks succeed with no manual help.**

## Environment

| Item | Value |
|---|---|
| Model | `nvidia/Qwen3.8-Flash-Next-NVFP4`, served as `qwen3.8-flash-next` (alias `spark`) |
| Quantization / context | NVFP4 (MoE, MTP layer); `max-model-len` 262144 |
| Hardware | 2x NVIDIA DGX Spark (GB10, 128 GB unified memory each), tensor parallel 2 with expert parallelism |
| vLLM | 0.32.0 |
| Launch flags (from the owner's model registry) | `--tensor-parallel-size 2 --enable-expert-parallel --all2all-backend allgather_reducescatter --gpu-memory-utilization 0.70 --max-num-seqs 8 --max-num-batched-tokens 8192 --max-model-len 262144 --speculative-config '{"method":"mtp","num_speculative_tokens":2}' --reasoning-parser qwen3 --enable-auto-tool-choice --tool-call-parser qwen3_coder --default-chat-template-kwargs '{"reasoning_effort": "low"}'`; served model names `qwen3.8-flash-next`, `spark` |
| Claude harness | `claude-agent-sdk` 0.2.180 with its bundled Claude Code CLI 2.1.321; `ANTHROPIC_BASE_URL` set to the vLLM server; Claude Code's own system prompt (`claude_code` preset); isolated config directory, no user or project settings |
| Fallback harness | `openai-agents` 0.24.0 (`openai` 3.49.0) on `/v1/chat/completions`, with its own read, write and shell tools |
| MCP | One stdio server (`mcp` 2.3.0, `shop_server.py`) used by both harnesses |
| Client machine | x86_64 development workstation, Python 3.14 |

## Task set

Ten scripted tasks (`tasks.py`). Each needs at least one MCP tool call, one shell command and one file edit, and has a deterministic checker that inspects only the final state of the task directory. The tasks cover a computed total with a stamp, a restock list, fixing code until unit tests pass, editing one line of a config file, moving files with shell commands, a git commit with a derived message, log counting against a threshold, filling JSON values, a Markdown report with a line count, and fixing a failing shell script from its error message.

All ten checkers were validated before any model ran: each passes a reference solution and fails the untouched task.

Each harness had at most 30 turns and 15 minutes per task, and one attempt per task. No manual help was given.

## Results

| | Claude Agent SDK on `/v1/messages` | OpenAI Agents SDK on `/v1/chat/completions` |
|---|---|---|
| **Pass** | **10/10** | **10/10** |
| Median turns (max) | 9 (13) | 6 (7) |
| Tool calls (of which MCP) | 77 (28) | 68 (27) |
| Malformed tool calls | 0 | 0 |
| Tool errors | 1 (expected: the deliberately failing first run of `sh greet.sh` in t10) | 0 |
| Stalls (turn limit or timeout) | 0 | 0 |
| Median seconds per task (total) | 20.3 (222) | 12.7 (129) |
| Input / output tokens, all tasks | 1,007,299 / 7,537 | 73,570 / 5,541 |
| Cache-read tokens reported | 0 | 0 |

Raw per-task records: `spikes/harness-vllm/results/claude-agent-sdk.jsonl` and `openai-agents.jsonl`.

## Findings

1. **Reasoning-effort mismatch (required configuration).** The first Claude run failed all ten tasks before the model did any work. vLLM rejected every request with `400 Unexpected reasoning effort high. Supported types are xhigh (default), medium, and low.` Claude Code sends effort `high` by default, and the Qwen chat template does not accept it. Pinning effort to `low` (SDK `effort="low"` plus `CLAUDE_CODE_EFFORT_LEVEL=low`, the model's own server default) fixed it. The failed run is kept as `results/claude-agent-sdk.run1-effort-high-rejected.jsonl`. This is configuration, not an adapter component, but it is mandatory: a worker template that runs Claude Code on this model must pin effort to a value the model's template accepts.
2. **Claude Code does not know the model.** Every run logged `[claude-code:unrecognized_model] {"model":"spark"}`. It did not stop the run, but Claude Code may then use default assumptions for this model, for example its context window when deciding to compact. Long sessions in Phase 1 must check this.
3. **Input-token cost is about 14 times the fallback's** (1.0 M versus 74 k for the same ten tasks). Claude Code sends its full system prompt and tool definitions on every turn, and took more turns (median 9 versus 6). vLLM reported no cache-read tokens. vLLM's own prefix caching may still have applied without being reported; that is not measured here. Wall time was about 1.6 times the fallback's.
4. **Tool calling through vLLM works in both API styles.** There were no malformed tool calls in 145 calls. MCP tools were used in every task, through both the Claude Code MCP client and the OpenAI Agents MCP client.

## Decision and consequences

**Go:** the Claude harness on vLLM's Anthropic endpoint is the primary path (plan §4.1 unchanged), with these consequences.

- **Phase 1 worker templates** pin reasoning effort per model (plan §2 already requires per-template limits and overrides). For this model the allowed values are `low`, `medium` and `xhigh`.
- **Cost units and budgets (§4.5)** must account for the harness's per-turn overhead. Phase 1 should measure whether vLLM prefix caching takes effect for Claude Code's repeated prefix, since that decides most of the cost difference.
- **Long sessions:** Phase 1's session and checkpoint tests should confirm how Claude Code behaves with a model it does not recognize (finding 2), especially near the context limit.
- **Fallback:** the `openai_agents` harness is measured, not assumed. On these tasks it is as reliable, faster and far cheaper in tokens, which keeps it a credible default if the harness licensing question in plan §2 (still open) goes the other way.
- **Benchmark suite:** these ten tasks and their checkers seed the Phase 1 agent benchmark suite.

## Limits of this evidence

- Ten short tasks, one attempt each, so no variance estimate. Both harnesses hit the ceiling, so the set does not separate them on reliability, only on cost and turns.
- One model at one effort level (`low`).
- Success means the checker passed. Output quality beyond the checked state was not reviewed.
- No long-running sessions, session resume, pod loss or context-limit behavior; those are Phase 1 tests.
- The agents ran with shell access in temporary directories on the owner's workstation, started by the owner, with no sandbox. The product needs the sandbox the plan requires before Phase 5.
