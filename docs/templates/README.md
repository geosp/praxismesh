# Document templates

| Template | Use for | Copy to |
|---|---|---|
| [rfc.md](rfc.md) | Full RFC: Phase 3A onward and material changes (plan §7.0, §4.17) | `docs/rfcs/phase-N-<topic>.md` |
| [rfc-short.md](rfc-short.md) | Short RFC: light-tier Phases 0-2 | `docs/rfcs/phase-N-<topic>.md` |
| [adr.md](adr.md) | One consequential architecture decision | `docs/adr/NNNN-<decision>.md` (next free number) |

`adr.md` is adapted from the MADR 4.0.0 minimal template (https://github.com/adr/madr), with MADR's Confirmation section and a Links section added. The MADR license is still to be verified and recorded here.

The `docs-design` skill (`.agents/skills/docs-design/`) uses these templates.

> [!NOTE]
> **Provisional.** These templates and the `docs-design` skill were brought forward from the Phase 0 documentation-skill task. They remain provisional until reviewed through the specialist review process (see the decision log). As-built architecture templates are still pending.
