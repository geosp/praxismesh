Review of /home/geo/develop/praxismesh/docs/plans/2026-11-17-event-transport-spike/plan.md (the only file I read)

## From the Summary
Phase 2 has to stream agent events to observers such as `agentctl tail`, and there are three candidate transports: Temporal Workflow Streams, a PostgreSQL event table, and NATS JetStream. The spike builds all three behind one interface, runs the same test suite and two workloads against each, and picks a winner with a rule set in advance (D2). The choice is made now because the first part of Phase 2, and anything that later reuses the interface, depends on it. The main risk is an unfair comparison caused by uneven effort or tuning, so the requirements, workloads and thresholds are fixed before any code is written.

## From the whole plan
The plan creates an isolated spike project, `spikes/event-transport/`, with its own uv project. It contains an `EventTransport` interface (publish / read-from-offset / latest), three implementations, a shared suite covering R1-R7, a committed recording of one real DSH task, and a synthetic load of 4 agents x ~50 token deltas/s x 5 min with 3 tailers each. Any option that passes R1-R7 can win. Among those, the plan prefers one that adds no new component and uses no preview API, and then the one with lower measured cost. The result is a report in `docs/spikes/` and a proposed ADR, and the losing implementations are deleted. The reasons given: the design prefers Workflow Streams, but Streams is still in Public Preview, adds history events, does not deduplicate retried attempts, and (like JetStream) does not document what a reader sees for an expired offset. Also, the plugin's built-in stream publishing no longer serves the main path now that `default` runs on DSH. No production code changes.

## How the existing system works, per this plan
Agents run on DSH, which ADR-0005 makes the primary harness inside Temporal Activities. Since phase 03 of a "DSH migration", the `default` (profile?) runs on DSH. Because of that, the OpenAI Agents plugin's built-in stream publishing no longer covers the main path. Events already follow an `AgentEvent` schema (`common/schemas/events.py`: seq, timestamp, workflow/task/attempt IDs, type, small payload). Attempt resets are signalled with `reset` events and `attempt_id`. The agent-to-agent inbox and `comms_mcp` use PostgreSQL. A local Compose stack provides Temporal and PostgreSQL. Current capacity is "two DSH pairs".

## Summary vs plan
- Major · Summary: "the requirements, workloads and thresholds are fixed here, before code (D3, D5)". D5 says the tuning parameters are in notes.md#d5, and R5's actual limits are only "verified in task 1.1". So two of the anti-bias controls are not fixed in this document. The citations are also off: the thresholds are in R5/R6, not D3/D5.
- Major · Summary leaves out why the design's stated preference (Workflow Streams) isn't simply adopted: Public Preview, history growth, no dedupe of retries, undocumented expiry. Without this, "we decide now" reads as scheduling, not as an open technical question.
- Major · Summary does not say the spike is isolated, makes no production change (R9, Non-goals), and ends by deleting the losers (D6). A reader of the Summary alone could assume the winner ships in this change.
- Nit · Summary: "Phase 2's first phase" is never identified anywhere in the plan.
- Nit · Summary diagram shows both workloads feeding the "shared suite". In the body, the suite tests the interface (R1-R4) and the workloads serve R5-R7.
- Nit · Summary says the rule is fixed, but D2 hands close calls to "the owner", and nothing defines what counts as close.

## Sections I couldn't fully paraphrase
I could paraphrase every section. Two had parts I could not explain, listed here as Major rather than Blocker:
- Major · Why, sentence 4 ("Since phase 03 of the DSH migration, `default` runs on DSH, so the OpenAI Agents plugin's built-in stream publishing no longer serves the main path"). I can repeat it but can't explain it. It doesn't say what `default` is, how the plugin related to Streams, or why this sentence matters to the decision.
- Major · D5. The mechanisms are clear, but the "parameters listed in notes.md#d5" are the core of the fairness control, and they are not in the plan.

## Undefined project-specific terms
- Major · DSH: never expanded or described, though it is central (recorded turn, capacity, migration).
- Major · "DSH pairs" / "today's capacity of two DSH pairs" (D3): this is the stated reason for rejecting a 16-agent stress level.
- Major · `default` (Why): profile, queue, or something else?
- Nit · "phase 03 of the DSH migration", and "as phase 03 verification did" (Risks).
- Nit · "OpenAI Agents plugin" and its "built-in stream publishing".
- Nit · `agentctl tail`, "the gateway", "the UI" (Summary).
- Nit · "recording sink" (D3): what it is and where it lives.
- Nit · `reset` events / attempt resets (D1).
- Nit · "the DSH spike" (D4), used as a precedent with no description.
- Nit · "the registry" (R9).
- Nit · `comms_mcp` (Non-goals).
- Nit · "the stack" / "shared dev stack" (D4, Risks).
- Nit · "the owner" (D2) and "the design review" (Risks): who they are.
- Nit · Design §4.3/§4.4, Phase 2 items 9/10/14, "Accept line": referenced only through Links.
- Nit · "task 1.1": lives in a phase file that isn't shown.

## Places where the parts don't connect
- Major · R4/R5 vs D1. The plan never says where publishing runs: inside a Workflow, an Activity, or a client. R5 (Temporal history) and R4 (Continue-As-New) only make sense for options that touch Workflow history. For the PostgreSQL and NATS options, it isn't said whether they are trivially met, how they are tested, or why they apply at all.
- Major · R5 threshold. "Under 10% of the limits verified in task 1.1": the limits and the resulting numbers are not in the plan, so a must-pass threshold depends on a later task.
- Major · R2 has no mechanism. Passing requires "events below offset B were removed", but the plan names no retention or trimming mechanism per option (the table, Streams, JetStream limits). It doesn't say how the test removes events, or whether forcing removal counts as tuning under D5.
- Major · D5 vs Risks vs D2. D5 limits each option to its "documented mechanisms". Risks says expiry code an option lacks "counts in the report". Why says Streams does not deduplicate retries, which R3 requires. It's unclear whether adding dedupe or expiry code on top of Streams is allowed or disqualifies it. "Extra code" also isn't one of D2's ranking criteria, so it's unclear how it counts.
- Major · D2's ordering is ambiguous, and in practice it favours one option. "No new component and no preview API": NATS is a new component and Streams is a preview API, so only PostgreSQL satisfies both. The plan doesn't say how the two preferences rank against each other (for example, NATS vs Streams if PostgreSQL fails), and doesn't acknowledge that the rule largely presets the answer if PostgreSQL passes.
- Major · D4 vs Risks/Impact. D4 says the spike uses "the stack's existing Temporal and PostgreSQL". Risks and Impact say measurements run in a "disposable Compose project". It's unclear which environment holds the spike schema and where the numbers come from.
- Major · Recording vs R9. The recorded turn needs a "recording sink" during a real DSH run. It isn't said whether that sink hooks into production code, which R9 forbids, or where it lives.
- Nit · D6's "operating-cost assessment" is not an input to D2's rule, so its role is unstated.
- Nit · R8 requires the same pass/fail results on rerun, but R6 latency near 1 s could flip between runs. No tolerance or repeat count is given.
- Nit · R9's "filtered to production paths": the production paths are never listed.
- Nit · Assumption "batch interval ~200 ms" reads like one of the D5 tuning parameters, which are said to be in notes.md. It's unclear whether it applies to all options or only Streams.
- Nit · Open questions says "None", yet R5's numbers and D5's parameters are still open in this document.

## Readability
- Nit · Why, sentence 2 ("A check on 2026-11-17 found ... which §4.4 requires us to report"): about 45 words, four findings joined by a semicolon. I had to reread it.
- Nit · D5, sentence 2: about 40 words in one list of per-option mechanisms. It would read better as a bullet list.
- Nit · R2 holds two rules: report the expiry with the base, and never skip silently. A third behaviour (then deliver from B) appears only in the Given/When/Then.
- Nit · R5 holds two limits (events and bytes), and "one synthetic agent's stream ... any single Workflow run" is ambiguous about per-agent versus per-run scope.
- Nit · R9 combines four prohibitions (packages, migrations, registry, Compose).
- Nit · D1 combines the interface shape, test scope and attempt-reset placement in one paragraph.
- Nit · The synthetic load is defined three times (Summary, Terms, D3), and only D3 gives the rate and duration.
- Nit · Offset semantics: Terms says "a reader resumes after it" and R1 says reconnecting from N yields N+1, but the D1 name `read(workflow_id, from_offset)` suggests the offset itself is included.
