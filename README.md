# PraxisMesh

**Durable orchestration for autonomous AI agents.**

PraxisMesh is an open-source, self-hosted platform that exposes an OpenAI-compatible API and runs agent work as durable [Temporal](https://temporal.io/) workflows. A request is triaged, planned as a task DAG when needed, dispatched to harness workers, verified, and delivered. Repository work arrives as a GitHub pull request.

> **Status: Phase 0.** The local platform stack (Temporal, database, object storage, model endpoints) runs with one command. No product code yet. See the [project plan](PROJECT_PLAN.md).

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
infra/                 local stack: docker-compose.yml, database init, .env.example
common/persistence/    application database migrations (Alembic)
Makefile               stack commands (make help)
tests/                 unit tests; tests/integration/ needs the local stack
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

You also need Docker with the Compose plugin to run the local stack (below).

### Checks

CI runs these on every pull request; the required check on `main` is `ci-ok`. Run them locally first:

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run pytest
uv run .agents/sync_agents.py --check
openspec validate --all
openspec update --dry-run      # expect "No changes"
gitleaks git --config .gitleaks.toml --redact .   # if gitleaks is installed
```

CI also lints the workflows with actionlint, checks internal links offline and, on pull requests, reviews new dependencies. The gitleaks and link checks each run a canary that proves they still catch a planted problem.

## Local stack

`infra/docker-compose.yml` runs the platform services PraxisMesh builds on, bound to `127.0.0.1` only. The design is in [docs/rfcs/phase-0-local-infrastructure.md](docs/rfcs/phase-0-local-infrastructure.md).

| Service | What it is | Address |
|---|---|---|
| `db` | ParadeDB (PostgreSQL 16 with `pg_search`): databases `temporal`, `temporal_visibility` and `praxismesh` | `127.0.0.1:5432` |
| `temporal` | Temporal Server 1.32 | `127.0.0.1:7233` |
| `temporal-ui` | Temporal Web UI | <http://127.0.0.1:8080> |
| `s3` | SeaweedFS with an S3-compatible endpoint | <http://127.0.0.1:8333> |

Two one-shot jobs, `temporal-schema` and `temporal-namespace`, set up Temporal's schema and namespace; both are safe to repeat. The model server (vLLM) is not part of the stack: it is an external endpoint you configure.

```bash
cp infra/.env.example infra/.env   # then edit: passwords, and VLLM_BASE_URL if you have a model server
make up                            # start and wait until healthy (safe to repeat)
make status                        # addresses, service health, model endpoint; fails if unhealthy
make migrate                       # apply application database migrations
make smoke                         # integration tests against the stack
make restart-check                 # a repeat start changes nothing; state survives down/up
make unhealthy-check               # a stopped database is reported by name
make down                          # stop, keep data
make reset                         # stop and delete all data volumes
```

`infra/.env` is git-ignored; keep hosts, passwords and keys there, never in the repository. Make never reads it: Docker Compose reads it with `--env-file`, and the tests and migrations get it through `uv run --env-file`. Write it as plain `KEY=value` lines using the names in `infra/.env.example`; values may use only `A-Z a-z 0-9 . _ : / @ % + , = -`. `make up` names whatever is wrong: Docker not running, `infra/.env` absent, a line that breaks these rules, or a required variable unset. A variable set in your shell overrides the file, except `COMPOSE_PROJECT_NAME`, which comes only from the file.

**Several checkouts.** Each checkout that runs its own stack needs its own `COMPOSE_PROJECT_NAME` (and its own ports) in its own `infra/.env`. `make` takes the name only from that file, never from your shell, so `make reset` in one checkout cannot reach another's stack; with no name in the file, every target refuses.

**Model endpoint.** Set `VLLM_BASE_URL` to the server's base URL without `/v1` (for example `http://<host>:8000`) and `VLLM_MODEL` to its served model name, which must not contain `/`. The model tests use both API styles at that URL: Anthropic Messages (`/v1/messages`) and OpenAI chat (`/v1/chat/completions`). With `VLLM_BASE_URL` empty they are skipped; set but unreachable, they fail and name the endpoint.

**When things go wrong.**

- `db` never becomes healthy after a first start: database init failed, or you changed a database password after the volume was created. Init runs only on a fresh volume, so run `make reset` (this deletes all data) and `make up`.
- A database volume created before the Phase 0 gate fixes is upgraded in place the first time its health check runs (marker and access revokes); no reset is needed.
- `TEMPORAL_RETENTION` takes `<number><s|m|h|d>`, for example `72h`. After you change it, `make up` updates the existing namespace.
- `make logs` follows every service's logs; `make status` exits 1 and names any unhealthy service.

**Trying the services by hand.** Load `infra/.env` in a throwaway shell, so its values do not linger in your usual one: run `bash`, then `set -a; . infra/.env; set +a`, then the commands below, then `exit`.

```bash
# Ask the model in each API style
# (drop the Authorization header if VLLM_API_KEY is empty)
curl -s "$VLLM_BASE_URL/v1/messages" -H 'content-type: application/json' -H "Authorization: Bearer $VLLM_API_KEY" \
  -d "{\"model\":\"$VLLM_MODEL\",\"max_tokens\":200,\"messages\":[{\"role\":\"user\",\"content\":\"Say hello\"}]}"
curl -s "$VLLM_BASE_URL/v1/chat/completions" -H 'content-type: application/json' -H "Authorization: Bearer $VLLM_API_KEY" \
  -d "{\"model\":\"$VLLM_MODEL\",\"max_tokens\":200,\"messages\":[{\"role\":\"user\",\"content\":\"Say hello\"}]}"

# Store, read and delete an object (boto3, from the project environment)
uv run python -c '
from tests.support.stack import s3_client
s3 = s3_client()
s3.create_bucket(Bucket="demo")
s3.put_object(Bucket="demo", Key="hello.txt", Body=b"hello")
print(s3.get_object(Bucket="demo", Key="hello.txt")["Body"].read())
s3.delete_object(Bucket="demo", Key="hello.txt")
s3.delete_bucket(Bucket="demo")
'

# Stop one service (Compose needs the file and env file from the repository root)
docker compose --env-file infra/.env -f infra/docker-compose.yml stop db
```

**Other object stores.** Code reaches storage through the S3 API, so another S3-compatible store works by changing the endpoint and keys:

- **Ceph RGW:** point the endpoint at the RADOS Gateway (for example `http://<rgw-host>:7480`) with an RGW user's access and secret keys; use path-style addressing.
- **Google Cloud Storage:** use the XML API's S3 interoperability endpoint `https://storage.googleapis.com` with an HMAC key pair for a service account.

Only SeaweedFS is run and tested in Phase 0.

**License note.** ParadeDB is AGPL-3.0. The stack runs it unmodified as a separate service, which does not change PraxisMesh's Apache-2.0 license; distributing a modified ParadeDB would carry AGPL obligations. See [docs/release.md](docs/release.md) and [ADR-0002](docs/adr/0002-paradedb-as-postgresql-server.md).

## Contributing

Work is tracked in GitHub issues and reaches `main` only through pull requests that pass `ci-ok`. See [CONTRIBUTING.md](CONTRIBUTING.md). Everyone taking part follows the [Code of Conduct](CODE_OF_CONDUCT.md).

## License

[Apache License 2.0](LICENSE).
