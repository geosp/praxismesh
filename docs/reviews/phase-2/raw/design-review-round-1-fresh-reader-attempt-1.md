<!-- Verbatim subagent report (design-review round 1, fresh reader, attempt 1, at 3e9df4a); reviewers: fresh-subagent (design-reader); saved by the coordinator per docs/reviews/README.md rule 1 (copied unchanged). Not a valid review: the file at 3e9df4a has 316 lines (git show 3e9df4a:docs/plans/2026-11-18-phase-2-events-and-comms/plan.md | wc -l), and the reader read only its first ~41. Retried per the skill (a reviewer that errors is retried once). -->

I could not do the review. The plan stops at line 41, and only its frontmatter, the Summary and the start of the "Why" section exist. This file has nothing to review beyond that:

/home/geo/develop/praxismesh/docs/plans/2026-11-18-phase-2-events-and-comms/plan.md

## From the Summary
The change makes agents observable and lets them message each other. Harness attempts write their events in batches to a PostgreSQL table, and `agentctl tail` follows a task live, resumes from an offset and reports expiry. A stdio MCP server, `comms_mcp`, lets an agent post a status, send a message or ask another task in the same request. A dispatcher wakes the recipient's `TaskWorkflow` with a Signal, and the workflow can now sleep in a `waiting` state until a message, a question deadline or an idle timeout. The Summary names two main risks: the cost of the per-task fence lock on every event batch, and a local model that ignores the ask-then-wait protocol.

## From the whole plan
I can't answer this from the whole plan because the whole plan doesn't exist yet. The text that does exist adds only the motivation: Phase 2 of the roadmap is next. A spike (issue #76) chose the table but left open the fence's lock order and cost, scoping, keying and token text. The owner settled four behaviour questions on 2026-11-18.

## How the existing system works, per this plan
Events go to a no-op sink (`harness_activity/events.py`), and only the DSH runner emits them. Nothing stores or displays them. A `TaskWorkflow` ends once its turns finish, so an agent can't receive a message or wait for one. Attempt writes are already fenced (ADR-0007). The plan doesn't say how.

## Summary vs plan
- Blocker, whole document: I can't compare the Summary with the plan because there is almost no plan to compare it with. The "Why" section breaks off mid-paragraph at line 40. There are no requirements (R1-R19), decisions (D3, D6-D11), phases, design, steps or acceptance criteria. The Summary cites all of these.
- Major, Summary vs Why: "Why" says the spike left the fence's lock order, scoping, keying and token text undecided. The Summary presents the fenced batch write as settled and doesn't mention those open questions.
- Major, Summary vs Why: "Why" says the owner settled D7, D8, D9 and D3's token rule. The Summary never mentions D9 or D3, and "token" appears nowhere else.

## Sections I couldn't paraphrase (each is a Blocker)
- Blocker, "Why": it stops after one paragraph, so it is cut off or unfinished.
- Blocker, every section after "Why": they are missing, including the three phases, the design behind D6/D7/D8/D11, and the R1-R19 list.

## Undefined project-specific terms
- Major, Summary: "fenced" and "fence" (ADR-0007) are never explained, and neither is what the "per-task fence lock" protects.
- Major, Summary: "harness attempt" and "turn" are not defined, nor is how they relate to each other.
- Major, Summary: "request", in "another task of the same request", is the unit that limits who can be messaged, but it is not defined.
- Major, Summary: "offset" and "expiry" for `agentctl tail` are not explained. What expires, and when?
- Major, Summary: "wake row" appears in the diagram but not in the text.
- Major, Summary: "inbox", "idle timeout" and "question deadline" have no source or value.
- Nit, Summary: `AgentEvent` is used without saying what it is.
- Nit, Why: "DSH runner" is used without saying what it is.
- Nit, Why: "D3's token rule" doesn't say which token.
- Nit, Summary: ADR-0007 and ADR-0009 are cited for content the plan never gives.
- Nit, Summary: "status" as a message kind is not distinguished from "message".

## Places where the parts don't connect
- Blocker, Summary: R1-R9, R10, R19, D6, D7, D8 and D11 are cited but never written down. There is no R11-R18 at all.
- Major, Summary: the "phase 01" measurement of the fence lock is promised, but there is no phase section, no threshold and no fallback if the cost is too high.
- Major, Summary: the "scripted fake model" mitigation has no acceptance-test section behind it.
- Major, Summary diagram: what turns the wake row into a dispatcher action is not stated. Nothing says whether the dispatcher polls or is notified, or who runs it.
- Major, Summary: there is no rule for the case where an asker waits and no reply comes before the question deadline.
- Nit, Summary: "the demo" is never described.

## Readability
- Nit, Summary, sentence 2: it has about 45 words, packs in three ideas and cites three references.
- Nit, Summary: "fenced like every other attempt write (ADR-0007)" needed a second read.
- Nit, Summary: "uses Continue-As-New while it waits" is unclear: the reader can't tell if the workflow restarts once or repeatedly.
- Nit, Summary: "post status, message or ask" can be read as a list of actions or as one noun, "post status".
- Nit, Why: the first sentence of "Why" mostly repeats the title, adding only the roadmap path.
- Nit, Summary: "R1-R9" is a range that holds many rules, and none of them is visible.

Before a reviewer can meaningfully re-run this, finish or restore the file: the rest of "Why", then the R and D lists, the phases and the acceptance criteria.
