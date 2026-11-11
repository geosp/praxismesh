# Contributing to PraxisMesh

Thank you for your interest. PraxisMesh is in its planning and bootstrap stage, so most work today is on the plan, specifications and project tooling. Please read this page before opening a pull request.

## Ground rules

- [PROJECT_PLAN.md](PROJECT_PLAN.md) governs scope, sequencing, constraints and gates. Approved OpenSpec specifications in `openspec/` govern detailed requirement text, and each requirement traces to plan sections (plan §4.16).
- Everyone follows the [Code of Conduct](CODE_OF_CONDUCT.md).
- Report security problems privately, as described in [SECURITY.md](SECURITY.md).

## How work flows

1. **Issue first.** Open or pick a GitHub issue for any non-trivial change. Use the issue forms; they ask for the phase, the plan sections and acceptance criteria.
2. **Branch** from `main` as `<type>/<issue>-<short-slug>`, where `<type>` is one of `feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `ci` or `spike` (for example `feat/42-blob-store`).
3. **Design before building** when a change is material. Write an RFC or ADR in `docs/rfcs/` or `docs/adr/` from the templates in `docs/templates/`, and propose requirement changes as an OpenSpec change.
4. **Commit** in small, reviewable steps. Commit messages describe the change. Do not add tool or agent attribution (no `Co-Authored-By` lines for tools, no "Generated with" footers).
5. **Check locally** before pushing (see "Checks" in the [README](README.md#checks)).
6. **Open a pull request** into `main`. The template asks for the issue, the plan and spec trace, the tests actually run and any demo evidence. Use `Closes #N` only for the issue the PR fully resolves; use `Part of #N` otherwise.
7. **Merge** happens by squash, only when the required `ci-ok` check passes and the branch is up to date with `main`. Review conversations must be resolved first.

## Reviews and phase gates

Each phase is closed by independent reviews and verification run in fresh sessions against a pinned commit, never by the author: design review, implementation review and verification. The protocol is in [docs/reviews/README.md](docs/reviews/README.md). A phase is complete only when its tests, acceptance criteria and demo all pass (plan §8).

## Working with coding agents

Agents follow [AGENTS.md](AGENTS.md). Shared skills and agent definitions live in `.agents/`; after changing an agent definition, run `uv run .agents/sync_agents.py`.

## License of contributions

PraxisMesh is licensed under the [Apache License 2.0](LICENSE). By submitting a contribution you agree that it is provided under the same license (Apache-2.0, section 5). There is no separate contributor license agreement.
