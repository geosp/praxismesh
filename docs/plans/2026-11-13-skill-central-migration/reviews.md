# Reviews · Centralize planning skills

Owner scope approval on 2026-11-13 is recorded in plan.md; it is not a
design-review verdict. No runtime phase closure is claimed.

## 2026-11-14 · impl-review · phase 03 · round 1 · passed

- Diff base: bfa79d1270ebba0f83fe3cf29d2abb7d448d37dd.
- Frozen code_sha: 5da23105ed20156e33b0a225dc3d3876218e5ddb.
- Reviewers: contract completed; failure/retry completed; scope/composition completed.
- [Independent report](../../reviews/skill-central-migration/implementation-01.md).
- Mechanical helper: zero errors/warnings through direct Python; uv cache-lock
  creation was blocked in the read-only review session. Public validator,
  agent generation and committed-range whitespace checks passed.
- Task 3.1 remains unticked; R1–R5 all have scenarios. No fresh tests or demo
  execution was claimed by the reviewer.

| ID | Severity | Reviewer | Contract | Finding | Resolution |
| --- | --- | --- | --- | --- | --- |
| F1 | Nit | Contract | R4 | Tests do not exercise human refusal with apparently complete metadata but unrun or mismatched execution evidence. | accepted: public validation deliberately checks structure only; coordinator must inspect execution evidence and SHA linkage under docs/reviews/README.md. A synthetic test cannot establish human enforcement. No execution proof is claimed by validator PASS. |
| F2 | Nit | Scope/composition | D3, R4 | A completed parent plan is accepted with unfinished phases. | fixed: check_plans.py rejects implemented/closed parents with phases outside done/abandoned; two regression cases failed before the fix and passed afterward; removing the fix made both fail again. Explicit abandonment remains supported. |

Later owner confirmation covers all supported harnesses in fresh Linux/macOS
sessions. The frozen report predates that confirmation. The independent
design-review record remains pending at this point.


## 2026-11-14 · design-review · phase 03 · round 1 · changes-requested

- Frozen design: 272eb64bbec7e4ceeaa521202096dbbb758b2f3b.
- Reviewers: reader completed; codebase-fit completed; zoom-out completed.
- [Independent report and verbatim paraphrases](../../reviews/skill-central-migration/design-01.md).
- Shared helper, public validator and generated-agent checks passed. The fresh
  reader opened only plan.md, but automatic project instructions were visible;
  the report discloses that limitation. No runtime closure is claimed.

| ID | Severity | Reviewer | Finding | Resolution |
| --- | --- | --- | --- | --- |
| F1 | Major | Codebase-fit, zoom-out | D2 conflicts with ADR-0003's mandatory Phase 4A RFC/OpenSpec artifacts. | fixed: proposed ADR-0004 supersedes the documentation requirement and carries all remaining ADR-0003 decisions forward; D2, task 3.1, phase-4a.md and decision log reference it. Fresh follow-up required. |
| F2 | Nit | Reader | Summary omits prerequisites and public validator replacement. | fixed: Summary names both. |
| F3 | Nit | Reader | Protected review, doctor, coordinator and latest-head approval lack definitions. | fixed: Terms defines each and links the operational authority. |
| F4 | Nit | Reader | Ownership and harness variants are unclear. | fixed: Terms defines them; D1 separates the Codex exception. |
| F5 | Nit | Reader | Validator scope is broad. | fixed: D3 lists coverage, scenarios, task verification and closure references, linking the public-validation specification. |
| F6 | Nit | Reader | Gate acceptance and rollout combine several independent rules. | fixed: R4 has separate scenarios; rollout and rollback use separate paragraphs. |
| F7 | Nit | Reader | Repository revert leaves installed shared-tooling state implicit. | fixed: rollback explicitly retains the central installation and describes manager-owned conflict recovery and its user-wide scope. |

All round-1 findings are resolved by the authoring changes; design-review status
remains changes-requested until fresh follow-up of the affected design.
