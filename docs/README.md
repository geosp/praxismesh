# Documentation map

Human-facing documentation for PraxisMesh. Requirements live in [`openspec/`](../openspec/); this folder holds the plan, designs, decisions, verified architecture and evidence (plan §4.17).

Phases 0 and 1 are complete. The [Phase 1 closure record](reviews/phase-1/closure.md)
links independent PASS reports, real-model evidence and the delivered revisions.
Phase 2 is next; its design and implementation have not started.

| Folder | What it holds | Written when |
|---|---|---|
| [plan/](plan/) | The detailed project plan; start from [PROJECT_PLAN.md](../PROJECT_PLAN.md) | Maintained throughout |
| [rfcs/](rfcs/README.md) | Proposed designs, one per phase or material change | Before implementation |
| [adr/](adr/README.md) | Architecture decision records | When a consequential decision is made |
| [architecture/](architecture/README.md) | As-built architecture of what actually runs | After implementation, verified before phase closure |
| [reviews/](reviews/README.md) | Independent review and verification reports, and the phase-gate protocol | At each phase gate |
| [demos/](demos/) | Phase demo evidence | When a phase demo runs |
| [templates/](templates/README.md) | Templates for RFCs, ADRs and review reports | - |
| [release.md](release.md) | Versioning, changelog and compatibility rules | Maintained throughout |

Folders the plan names for later phases (`spikes/`, `benchmarks/`, `security/`, `api/`, `operations/`) are created when their first document is written.
