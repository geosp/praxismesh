<!-- Verbatim subagent report (design-review round 4, fresh reader, targeted follow-up on the phase 02 decision changes); saved by the coordinator per docs/reviews/README.md rule 1; local paths replaced by <repo>. -->

Review of <repo>/docs/plans/2026-11-15-dsh-production-harness/plan.md (I read only this file)

## From the Summary
The change makes DeepSeek Harness (DSH) the runtime for PraxisMesh agent turns before roadmap Phase 2, so Phase 2's event streaming only has to be built once, on DSH. Temporal still handles dispatch and retries. Each worker gets a paired DSH container with no credentials and no network. A launcher in that container isolates each attempt by cgroup, UID and mount view. The worker keeps the credentials, model gateway and tool executor. Both runners share one checkpoint seam with a fence, workers check pinned DSH digests, and a migration records unknown usage and charges lost requests conservatively. The main risks are that the in-house checkpoint barrier may fail when real workers are lost, and that DSH was about 1.9x slower in the spike. The `default` profile switches only after a benchmark passes and the owner approves.

## From the whole plan
The plan ports the spike's DSH integration into production code (`harness_activity/dsh/`). It adds a `dsh` harness value, a `local-dsh` template and a `dsh` profile, all behind a session/checkpoint seam that `openai_agents` also uses and must still pass through (conformance suite plus baseline benchmark). The reason is to meet ADR-0005's five adoption conditions, which the spike proved only in isolation: a pinned release, a checkpoint consistency contract, a per-attempt isolation boundary with model and tool use observed outside it, production capability semantics, and `openai_agents` staying selectable. The supporting work is:
- a barrier (D6) that freezes the attempt before committing a checkpoint
- a transactional fence (D10) against stale attempts
- a gateway usage ledger with explicit unknown usage and a conservative charge for lost requests (D7, D9)
- a minimal AgentEvent sink that Phase 2 will replace (D8)

The `default` profile moves to DSH only in phase 03, after R19 and owner approval.

## How the existing system works, per this plan
Agent turns run as Temporal Activities through `run_harness_turn` with the `openai_agents` runner (a `HarnessRunner`). The conversation lives in an OpenAI SDK `SQLAlchemySession`. Checkpoints record a `session_position` and point to a workspace tarball, and on resume, items after that position are dropped. The registry defines profiles (which templates are allowed, limits) and templates (capabilities, harness), pinned by a registry lock. `local-default` is the existing template, with a 10/10 benchmark baseline. Tool bodies currently live inside `FunctionTool`. Attempt rows currently store token counts, apparently as 0 when unknown (spike findings F1/F2). The plan says little else about the current state; phases 01 and 02 are already marked done or in progress, so part of the "current" system is already this plan's work.

## Summary vs plan
- Major (Summary vs D8/R16): The Summary's stated reason is Phase 2 event streaming, but it never mentions the AgentEvent sink (D8) or that the gateway and executor emit events (R16). That is the mechanism that serves the reason.
- Major (Summary vs Rollout & rollback): The Summary leaves out that code rollback past the D7 migration is not supported, and that DSH tasks already running must finish on DSH because `openai_agents` cannot resume a DSH checkpoint. Both are needed to judge the risk.
- Major (Summary/front matter vs Decision log): The front matter says `design_review: changes-requested` and also `approved`. The decision log says "A targeted design review is due", but Open questions says "None". The Summary gives no hint that the design is not settled.
- Nit (Summary vs R3/R4): Requirements R3 and R4 say `openai_agents` must still pass conformance and the baseline. The Summary only implies this ("both runners share one seam").
- Nit (Summary vs R17/Decision log): The Summary says workers check digests. The decision log widens this to the container's control files, re-checked at every attempt.
- Nit (Summary vs D9): The Summary says lost requests are "charged conservatively" but not that the turn then retries, which is the point of D9 (it replaces fail-closed denial).
- Nit (Summary vs Risks): The Summary names 2 of the 4 risks. It omits pre-release runtime churn, process escape from the attempt boundary, and the ~30% extra input tokens.
- Nit (Summary vs D3): The Summary omits that the launcher holds `SYS_ADMIN` (decision log). That is a security-relevant property of the "credential-free" container.

## Sections I couldn't paraphrase
No section is fully unparaphrasable, so there are no Blockers. Several sections can only be paraphrased at headline level because their substance lives in notes.md:
- Major, D6: "require the newest tool-call ID in the session files" does not say which ID or what "require" checks (wait? fail?). Retries, timeouts and the SIGSTOP fallback are in notes.md#d6.
- Major, D3 / D4 / R14: The confinement settings and the list of disabled features are only in notes.md. For R14 the list can be partly recovered from the Why table.
- Major, D10: "refusal rows" (decision log) and how a stale attempt's start is refused or recorded are not described.

## Undefined project-specific terms
All Nit unless noted.
- Major: "turn" vs "attempt" vs "task". The core hierarchy is never defined. "Inner turns" and the "inner-limit" case add a third meaning of "turn".
- Major: "settled" / "unsettled" ledger row (R11, R12, D9). These drive the billing rules.
- "Shop tool" (Summary, Terms: Executor). The meaning of "shop" is never given.
- "Conformance suite" (R3).
- "Registry lock" (R1, R17).
- `TurnOutcome`, TaskResult contract (R7, R18).
- The R18 outcome cases: plain-text, invalid-reference, retry-protocol, lost-after-finish, and others. Each is only a label pointing to an external evidence JSON.
- "The run path" (R6), "publishes" (R7), "the window" (R8), "grace" (R8 title, before R9 explains it).
- Spike findings F1/F2 (D7) and "the spike's fail-closed denial" (D9).
- `concurrency_per_pod`, `allowed_templates`, `max_wall_time`, `context_window`, queue `tpl.local-dsh`.
- "Control files" (decision log, R17).
- "Phase 01 gate", "phase 01 task 0.1", "phase 03 task 2.1". These point to phase files.
- "Code rollback below D7".
- ADR-0005's "condition 3". The Why table paraphrases it, but which row is condition 3 is only inferable.

## Places where the parts don't connect
- Major, R12 vs Terms: A lost attempt is defined as one that "ended without writing its attempt row". Yet R12 expects "that attempt row" (apparently the next attempt's row) to have null tokens. It is unclear whose row carries the unknown usage and who writes it.
- Major, R13 vs decision log D9: R13 charges "before the turn retries". The log adds "charged at the failure when no later attempt runs", which no requirement covers.
- Major, R17 vs decision log: The requirement and its test check only at worker start. The log says re-checked at every attempt, and that the pin covers control files. The requirement was not updated.
- Major, D4 vs decision log: D4 was "restated" in the log (UID, capabilities, seccomp, mount view, per-attempt `/tmp`), but D4's body still defers to notes.md and R15 doesn't test `/tmp` isolation.
- Major, D3 vs decision log: The `SYS_ADMIN` requirement and the seccomp ban on user namespaces live only in a log entry, not in D3 or Risks.
- Major, Summary/D3 vs R16/Terms: The DSH container has "no network", yet model requests go to a worker-side gateway and tool calls go to a worker-side executor. The transport between the containers is never stated. The shared tmpfs is the only channel mentioned.
- Major, R10: There is no mechanism for how the launcher detects worker death within 10 s.
- Major, D1: `session_position` "stays 0" for DSH, but the plan never says how DSH truncates or resumes a session blob, or why 0 is safe.
- Major, D11 vs R18: D11 says R18 counts include retried or lost attempts' steps, "added to the spike's counts". R18 says results must match the spike evidence JSON. It is unclear whether the JSON already reflects D11 or whether matching is not exact.
- Nit, Assumptions: Under the SIGSTOP fallback, it is not stated whether D6 and R8 still hold.
- Nit, Rollout & rollback: "DSH tasks already running finish on DSH" assumes DSH workers stay deployed during the drain. This is not stated.
- Nit, Why table: R1, R2, R12, R13, R16, R18 and R19 are not mapped to any condition. R16/D8 are justified only by Phase 2.
- Nit, Phases table: Phase 02 shows "in-progress" with 8/8 tasks.

## Readability
- Nit, Summary: I had to reread "The worker keeps the Activity, credentials, model gateway and the executor that runs file and shop tool bodies; commands run in the attempt's cgroup." It is unclear whether commands are run by the executor or by the DSH process.
- Nit, Decision log 2026-11-16 entry: One run-on sentence of over 60 words with four separate changes. The 2026-11-15 second entry is also dense and packs several rules.
- Nit, Terms "Current / stale / lost attempt" and "Profile / template": slash-paired definitions that I had to reread to match each term to its definition.
- Nit, R8: Two rules (exit within 5 s; nothing started runs in the next 10 s) and three triggers in one requirement.
- Nit, R7: Two rules (no artifact or outcome; staleness judged at the fenced write).
- Nit, R15: Two rules (cannot read the session or other trees; background processes die with the attempt).
- Nit, R11, R12, R16: Each combines two rules (token vs tool usage; null tokens plus a flag; executor events vs gateway events).
- Nit, duplication:
  - "Committed only after the barrier" appears in Terms, R5 and D6.
  - The stale-attempt rule appears in R6, R7 and D10.
  - `usage_known` appears in D7, R12 and Impact.
  - The D9 output cap appears in D9 and again in the log.
- Nit, Rollout & rollback: "Code rollback below D7 is not supported" is ambiguous ("below" in what order?).
