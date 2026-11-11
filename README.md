# PraxisMesh

**Durable orchestration for autonomous AI agents.**

PraxisMesh is an open-source, self-hosted platform that exposes an OpenAI-compatible API and runs agent work as durable [Temporal](https://temporal.io/) workflows. A request is triaged, planned as a task DAG when needed, dispatched to harness workers, verified, and delivered. Repository work arrives as a GitHub pull request.

> **Status: planning.** No implementation exists yet. The project is in its bootstrap stage: plan, tooling, CI and review process. See the [project plan](PROJECT_PLAN.md).

## Where to start

| You want to | Read |
|---|---|
| Understand what is being built and in what order | [PROJECT_PLAN.md](PROJECT_PLAN.md), the core plan with a document map |
| Find a design document, decision or review | [docs/README.md](docs/README.md) |
| Contribute | [CONTRIBUTING.md](CONTRIBUTING.md) |
| Report a security problem | [SECURITY.md](SECURITY.md) (privately, never in a public issue) |
| Work on this repository with a coding agent | [AGENTS.md](AGENTS.md) and [.agents/README.md](.agents/README.md) |

## Repository layout

```
PROJECT_PLAN.md        core plan; detail in docs/plan/
docs/                  plan, RFCs, ADRs, architecture, reviews, demos, templates
openspec/              OpenSpec specifications and changes
.agents/               skills and agent definitions shared by Claude Code, Copilot and Codex
.github/               CI workflows, issue and PR templates, CODEOWNERS
tests/                 tests for the repository's own tooling
```

Product code (gateway, orchestrator, workers and so on) arrives phase by phase; its planned layout is in [PROJECT_PLAN.md](PROJECT_PLAN.md) §6.

## Getting started

### Prerequisites

- `git` and the GitHub CLI `gh` (logged in with `gh auth login`)
- [`uv`](https://docs.astral.sh/uv/) for Python
- [`fnm`](https://github.com/Schniz/fnm) (or another Node version manager) for Node.js, which the OpenSpec CLI needs

### Set up

```bash
git clone https://github.com/geosp/praxismesh.git
cd praxismesh

# Python: the project targets 3.11 or newer and tests on 3.11 (.python-version)
uv python install 3.11
uv sync --locked

# Node: version from .node-version; add fnm's shell hook so it is on PATH in new shells
fnm install
line='eval "$(fnm env --use-on-cd --version-file-strategy=recursive --shell bash)"'
grep -qxF "$line" ~/.bashrc || echo "$line" >> ~/.bashrc
source ~/.bashrc

# OpenSpec CLI, pinned, with the settings this repository uses
npm install -g @fission-ai/openspec@1.17.0
openspec config set telemetry.enabled false
openspec config set delivery skills
openspec --version
```

The OpenSpec settings are per machine (`~/.config/openspec/`). This repository uses only OpenSpec's shared `agents` target. Refresh the generated skills with `openspec update`; never re-run `openspec init` with other tool IDs. See [.agents/skills/README.md](.agents/skills/README.md).

Model servers are not needed yet. When they are, their endpoints go in a local, git-ignored `.env`, never in the repository.

### Checks

CI runs these on every pull request; the required check on `main` is `ci-ok`. Run them locally first:

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run pytest
uv run .agents/sync_agents.py --check
openspec validate --all
```

## Contributing

Work is tracked in GitHub issues and reaches `main` only through pull requests that pass `ci-ok`. See [CONTRIBUTING.md](CONTRIBUTING.md). Everyone taking part follows the [Code of Conduct](CODE_OF_CONDUCT.md).

## License

[Apache License 2.0](LICENSE).
