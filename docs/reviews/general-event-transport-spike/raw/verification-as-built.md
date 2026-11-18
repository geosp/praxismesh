<!-- Verbatim verifier report (event-transport spike verification, as-built claims, code_sha = docs_sha 8153e7b8dd534da06fb4a16f9a7dd8c78ff4829a); fresh verifier subagent; saved by the coordinator per docs/reviews/README.md rule 1 (copied unchanged). -->

# As-built documentation check: event-transport spike (issue #76)

- Frozen code: `/tmp/claude-1000/-home-geo-develop-praxismesh/599639d3-a59f-4a32-945c-fd5372c3c537/scratchpad/verify-76` at `8153e7b8dd534da06fb4a16f9a7dd8c78ff4829a`. Deleted options read at `1bfac67`; load runners read at `c1fda62` and `5854ca2`.
- Results were recomputed from the **committed** files (`git archive 8153e7b spikes/event-transport/results`, extracted to `.verify/asbuilt/res/`). The checkout's working copies of 9 results files were already modified by an earlier check, so they were not used.
- Recompute script: `.verify/asbuilt/scripts/compute.py`, output in `.verify/asbuilt/compute.out`. Other evidence: `.verify/asbuilt/status.log`, `db.log`, `suite.log`, `suite/`, `up.log`, `scripts/f55.py`.
- I changed nothing in source, tests or docs. The only writes outside `.verify/` were to the disposable `pmspike76` stack: `make up` (idempotent) and one run of the shared suite, which uses the `spike76` schema and wrote its results file under `.verify/asbuilt/suite`. `git status` afterwards showed only the 9 pre-existing results modifications and `.verify/`.
- Documents checked: `docs/spikes/event-transport.md` (SR), `docs/adr/0009-...md` (ADR), `spikes/event-transport/README.md` (RM), `spikes/event-transport/probes/README.md` (PR), `docs/roadmap/decision-log.md` row at line 9 (DL; the only 2026-11-18 row), and `docs/plans/2026-11-17-event-transport-spike/notes.md` "Verified" section, lines 3-64 (NV). None of these files differ between the checkout and 8153e7b.

## Verdict summary

No Blockers and no Majors. Every figure in the measurement tables recomputes from the committed results files. Every version, port, schema element, mechanism and line count matches the code or the running stack. The findings are all Nits:
- 10 imprecise, overgeneralised or inconsistent statements;
- 4 places where future behaviour is stated as current;
- 6 claims that cannot be checked (probe outputs that were never committed, external documentation, hedged inferences).

## Runtime probes run (documented commands, or read-only queries)

| Command | Expected | Observed |
| --- | --- | --- |
| `make status ENV_FILE=spikes/event-transport/stack.env` | RM: Temporal 37233, UI 38080, PostgreSQL 35432, S3 38333 | `addresses: Temporal 127.0.0.1:37233, UI http://127.0.0.1:38080, S3 http://127.0.0.1:38333, DB 127.0.0.1:35432` / `all services healthy` |
| `cd spikes/event-transport && uv sync --locked` (RM setup) | succeeds | `Resolved 18 packages ... Checked 16 packages` |
| `make up ENV_FILE=spikes/event-transport/stack.env` (RM setup) | stack up | `stack is up; run 'make status' for addresses and health` |
| `docker compose -p pmspike76 ps --format '{{.Name}} {{.Ports}}'` | ports bound to 127.0.0.1 | `pmspike76-db-1 127.0.0.1:35432->5432/tcp`, `pmspike76-temporal-1 127.0.0.1:37233->7233/tcp`, `pmspike76-temporal-ui-1 127.0.0.1:38080->8080/tcp`, `pmspike76-s3-1 ... 127.0.0.1:38333->8333/tcp`; no NATS container |
| `docker exec pmspike76-db-1 psql -U praxismesh -d praxismesh -Atc "select version()" ...` | SR: ParadeDB 0.26.6, PostgreSQL 16; table: app role, `spike76` schema | `PostgreSQL 16.15 ...`; `pg_search` `0.26.6`; `praxismesh|f` (not a superuser); tables `spike76.batches`, `spike76.counters`, `spike76.events` owned by `praxismesh`; `events` columns `workflow_id text`, `offset bigint`, `body jsonb` |
| `docker exec pmspike76-temporal-1 temporal-server --version` | SR: Temporal server 1.32.2 | `temporal version 1.32.2` |
| `env -u VIRTUAL_ENV SPIKE_TRANSPORTS=memory,table SUITE_HORIZON_S=60 SPIKE_RESULTS=../../.verify/asbuilt/suite uv run pytest -q -p no:cacheprovider tests/test_suite.py tests/test_table_notify.py` | ADR: the table passes R1, R2, R3 and R7 behind the interface | `15 passed, 2 skipped in 113.31s`; `suite-table.json` `"R1": "pass", "R2": "pass", "R3": "pass", "R4": "n/a", "R7": "pass"`, commit 8153e7b, `dirty: false` |
| `uv run python .verify/asbuilt/scripts/f55.py` (memory transport, in process): publish 10 events, `expire_below(11)`, then a fresh `read(after=5)` | SR:123 says a removal through the end of the log yields no expiry until a later event | `[Expired(retained_base=11)]`: a fresh read does report it (see N2) |

## Recomputed figures (committed results at 8153e7b)

All 9 load files and all 6 c1fda62/5854ca2 suite files show `dirty: false` and the commit the docs name (`c1fda62...` or `5854ca2...`). Params are 300 s, 4 agents, 3 tailers, 50/s, batch 0.2 s / 64.

| Doc figure (SR:52-64 unless noted) | Recomputed: runs 1, 2, 3 then median (range) | Status |
| --- | --- | --- |
| Offered 60,232 | `load.py`:100-130 at 8153e7b: 15,000 tokens plus 29 tool pairs (at 10, 20, ..., 290 s) = 15,058 per agent, x4 = 60,232. Tailer `latest` is 15058 in every open-loop run | confirmed |
| Streams published 54,897 (54,889-54,956) | 54897, 54956, 54889 | confirmed |
| Table published 58,002 (57,811-58,059) | 57811, 58059, 58002 | confirmed |
| Open-loop published 60,232 (all runs) | 60232 x3 | confirmed |
| Publish p50: 13.4 (13.1-13.7) / 4.3 (4.3-4.4) / 4.3 (4.2-4.3) ms | 13.70, 13.10, 13.45 / 4.35, 4.32, 4.26 / 4.26, 4.25, 4.24 | confirmed |
| Publish p95: 23.8 (18.4-26.9) / 5.5 (5.4-6.1) / 5.7 (5.7-5.8) | 26.91, 18.38, 23.79 / 5.54, 6.06, 5.40 / 5.80, 5.66, 5.69 | confirmed |
| Latency p50: 113 (113-114) / 92 (92-104) / 110 (109-110) | 113.48, 113.01, 113.51 / 91.59, 91.82, 103.55 / 109.62, 109.79, 109.41 | confirmed |
| Latency p95: 199 (199-200) / 187 (187-188) / 204 (204-204); also SR:34, ADR:48-50 | 198.92, 199.60, 199.04 / 187.79, 186.80, 187.12 / 204.00, 204.45, 203.64 | confirmed |
| Latency p99: 326 (326-372) / 189 (188-190) / 214 (213-214) | 326.49, 371.56, 326.44 / 190.11, 188.48, 188.83 / 213.57, 213.84, 213.12 | confirmed |
| Latency max: 1,225 (1,218-1,227) / 222 (218-227) / 224 (223-227) | 1227.1, 1217.8, 1225.1 / 222.3, 226.5, 217.5 / 223.2, 227.4, 224.4 | confirmed |
| Tailers complete, no expiries | `complete: true` x9; 12 tailers per run; `expired` empty everywhere; no `error`; killable tailers `restarts` 5 | confirmed |
| Temporal CPU, median of run medians: 32.4 (32.1-32.6) / 1.4 (1.4-1.6) / 1.3 (1.2-1.8) | 32.64, 32.08, 32.41 / 1.58, 1.41, 1.43 / 1.845, 1.24, 1.27 (`pmspike76-temporal-1` samples, 25-26 per run) | confirmed |
| Temporal CPU peak: 185 (39-204) / 3 (3-15) / 13 (13-21) | 204.0, 39.02, 184.9 / 3.11, 14.9, 3.21 / 20.68, 12.96, 13.35 | confirmed |
| PostgreSQL CPU median: 12.8 (12.1-13.1) / 4.0 (3.2-7.1) / 3.3 (3.2-3.3) | 13.06, 12.79, 12.11 / 3.18, 3.95, 7.10 / 3.335, 3.33, 3.24 | confirmed |
| SR:76 table DB CPU "drifted from 3.2% to 7.1% across runs"; open-loop steady | in time order 3.18, then 3.95, then 7.10 (05:39, 05:51, 06:03); open-loop 3.335, 3.33, 3.24 | confirmed |
| SR:78-79, SR:138, SR:164, ADR:42 Temporal CPU "~20-23x" (32.1-32.6 against 1.4-1.6) | per run 20.7x, 22.8x, 22.7x; extremes 20.3-23.1x | confirmed |
| SR:79, SR:138 PostgreSQL "3.2x (1.7-4.1x)" | median ratio 3.24; per run 4.11, 3.24, 1.71 | confirmed |
| SR:68 Streams "~5% less load" | 54,897 / 58,002 = 0.946, so 5.4% less | confirmed |
| SR:60 8 hosting runs per agent, a roll-over every ~40 s | 8 runs in each of the 12 chains; start-to-start intervals 41.7-46.4 s, median 42.3 s | confirmed |
| SR:61, SR:98-99, NV(D5) 135-136: 84 completed runs, 3,232-3,531 events, 4.44-4.50 MB, 757-827 Updates, 191-207 batches | 12 chains x 7 = 84; events 3232-3531; bytes 4,442,795-4,495,354; Updates (poll + publish) 757-827; `publish_batch` 191-207 | confirmed |
| SR:33 R5 3,519 (3,519-3,531), 4.50 MB, bounds 5,120 events and 5 MiB | `max_run_events` 3531, 3519, 3519; `max_run_bytes` 4,495,354 in every run; bounds `LIMIT_EVENTS*0.1` = 5120 and `LIMIT_BYTES*0.1` = 5,242,880 (load.py:53, 223 at 8153e7b; load-c1fda62.py:53, 313) | confirmed |
| SR:39, SR:109-111 R11 298 KB, ~8 KB per roll-over, 248 to 298 KB, ~360 KB at 600 s | `max_carried_bytes` 297764, 297696, 297765; run1 a0 chain `[104, 248476, 256405, 264334, 272258, 280153, 289640, 297690]` (steps 7.9-9.5 KB); about 7 more roll-overs to 600 s gives ~356 KB; bound 1 MiB (load.py:229) | confirmed; the 600 s figure is an extrapolation and is labelled as one |
| SR:88-90, PR:11, NV 130-132 growth: ~1.85 min, 2,000 Updates (~500 publish, ~1,500 poll), ~8,500 events, ~10.2 MB, ~4,600 events and ~5.5 MB per minute | provenance file runs e47794c1-a0..a3: 1.89/1.84/1.83/1.84 min; poll 1499-1500 plus publish 500-501 = 2000; 8505-8510 events; 10.16-10.18 MB; 4504-4638 events/min; 5.38-5.55 MB/min | confirmed |
| SR:92-94, PR:11 provenance names the probe's commit and command; the raw file lists 12 extra runs | provenance: `"commit": "36ebee0 ..."`, `"command": "PYTHONPATH=. uv run python probes/streams_update_limit.py > ..."`; raw file has 16 entries, 12 of them from fb809c98, 3c994f04, 5e40dd37 | confirmed |
| SR:29-36 R1, R2, R3, R7 pass 3/3 (Streams, table, open-loop); R4 pass 3/3 (Streams) | `results/run{1,2,3}/suite-{streams,table}.json` (c1fda62) and `open{1,2,3}/suite-table.json` (5854ca2) all pass; table R4 `n/a` | confirmed |
| SR:34 R6 pass 3/3 for every load set; SR:33, SR:39 R5 and R11 pass 3/3 for Streams | `requirements` in every load file: R6 pass; Streams R5 and R11 pass; table R5 and R11 `n/a` | confirmed |
| SR:36 R8 "every pass/fail matches across 3 runs" | identical requirement maps across runs in each set | confirmed |
| SR:17, SR:29-35, ADR:61 NATS passed the suite; SR:36 single run at 69c95c4, before `check_r1_cancel` | `suite-nats.json`: commit 69c95c4, R1, R2, R3, R7 pass, R4 n/a; `check_r1_cancel` was first added in 5ae0731, which descends from 69c95c4 (`git merge-base --is-ancestor`) | confirmed (see N12 for the ADR) |
| SR:37 R9 "the diff outside `spikes/` and `docs/` is empty"; RM:10-11 | `git diff --stat $(git merge-base main 8153e7b) 8153e7b -- . ':!spikes' ':!docs'` prints nothing; the full diff is 73 files, 11,020 insertions | confirmed |

## Code, version and configuration claims

| Claim (location) | Evidence | Status |
| --- | --- | --- |
| Versions: ParadeDB 0.26.6 (PG16), asyncpg 0.32.0, Temporal 1.32.2, temporalio 1.36.0, nats-server 2.15.3, nats-py 2.17.0 (SR:7-8, DL, PR:9) | `infra/docker-compose.yml`:14, 51; spike `uv.lock` at 8153e7b, 1bfac67 and c1fda62; `nats.compose.yml` at 1bfac67 pins `nats:2.15.3`; live probes above | confirmed |
| Comparison at c1fda62 without resets; open-loop at 5854ca2 with a stack reset before each run (SR:4-5, SR:75-77) | `measure.sh` at c1fda62 has no reset; `measure.sh` at 5854ca2:12-18 resets before each run; Streams runs left Running during later runs appear in `streams-growth-norollover.json` (12 runs) | confirmed |
| Streams and NATS deleted; in history at 1bfac67 (SR:22-23, RM:9-10, PR:3-4, `factories.py`:3-4) | the 8153e7b tree has no streams, jetstream or nats files; `OPTIONS` = memory and table only (`factories.py`:37-40); the files exist at 1bfac67 | confirmed |
| Spike code 314 / 183 / 131 lines plus a Compose file (SR:139, SR:165, ADR:45-46, DL) | at 1bfac67 `streams.py` 199 + `streams_workflow.py` 115 = 314; `table.py` 183 (unchanged at 8153e7b); `jetstream.py` 131; `nats.compose.yml` present | confirmed (see N5 for the ADR wording) |
| Streams parts: custom publish Update with batch-ID dedup, `retained_base` Query, Update-only reads mapping `TruncatedOffset`, cancellation fix, private decoder (SR:133, SR:139, NV) | 1bfac67 `streams_workflow.py`:87-97, 109-111; `streams.py`:140-150, 107-109, 28 (`from temporalio.contrib.workflow_streams._types import _decode_payload`) | confirmed |
| Streams roll-over on suggestion or every 2,000 batches, keeping the last 500; carried state = log plus batch-ID set (SR:98, SR:108) | `streams_workflow.py`:22-23, 59-85 | confirmed |
| 2 h execution timeout on the chain; fixed task queue (SR:140, NV) | `streams.py`:42, 44, 86 | confirmed (that the Temporal timeout spans the chain is Temporal semantics, not observed) |
| Table: counter row locked on publish (gap-free), batch row in the same transaction, one `NOTIFY` per batch, `LISTEN`, clear before fetch, 1 s poll (ADR:54-58, SR:139) | `table.py`:71-104 (`FOR UPDATE` at 77, batch insert at 89-94, `pg_notify` at 104), 135, 145, 154-155, `POLL_S = 1.0` at 31 | confirmed |
| Every reader reports a jump as `Expired` and raises on a repeat (ADR:59, SR:118) | `transport.py`:218-235; `table.py`:124 and `memory.py`:44 use `guarded`; at 1bfac67 `streams.py`:124 and `jetstream.py`:74 also do | confirmed (see N3 on attribution) |
| Pool max 20; one connection per follower; publishers share the pool (ADR:72, SR:140, NV) | `table.py`:61 `max_size=20`; 127 (connection held for the whole read); `load.py`:258-287 (one transport for agents and tailers) | confirmed (see N6) |
| One global `NOTIFY` channel (ADR:74, SR:140) | `table.py`:29 `CHANNEL = "spike76_events"` | confirmed (see N7 on "wakes") |
| NATS: a stream per workflow, pull consumer, purge-aware reads, 60 s idle expiry, file storage, 1 replica, its own volume (SR:134, 139-140) | 1bfac67 `jetstream.py`:40, 45-53, 88-97 (`inactive_threshold=60.0`), 110-113; `nats.compose.yml` volume `jetstream` | confirmed |
| Open-loop runner: fixed schedule, stamped when due, 10 ms flush poll; batch IDs `<workflow>:<attempt>:<n>` (SR:71-73, SR:126) | `load.py`:100-112, 148, 141 | confirmed |
| Closed-loop runner at c1fda62: awaited each publish; time blocked in a publish not counted (SR:67-69) | `load-c1fda62.py`:97-129 (inline `await`, timestamp taken at creation, `sleep(1/RATE)`) | confirmed |
| History bytes = sum of each fetched event's `ByteSize()`; `SpikeLoadAgent` runs not measured (SR:80-82) | `load-c1fda62.py`:198-200; only `spike76-stream-*` IDs are listed (189-190) | confirmed |
| PostgreSQL CPU under Streams is Temporal's persistence (SR:64) | `infra/docker-compose.yml`:55 `POSTGRES_SEEDS: db` | confirmed |
| `stack.env` = `.env.example` plus project name and ports (RM:30-31) | `diff infra/.env.example spikes/event-transport/stack.env`: `COMPOSE_PROJECT_NAME`, `DB_PORT`, `TEMPORAL_PORT`, `TEMPORAL_UI_PORT`, `S3_PORT`, plus `PRAXIS_SAMPLE_DB_URL` (the port inside it) | confirmed |
| `make reset` removes the stack and its data (RM:32) | `Makefile`:93-96 `down --volumes --remove-orphans` (not run, to keep the stack up) | confirmed from code |
| Streams backups depend on `TEMPORAL_RETENTION` (SR:134) | `stack.env`:31 `TEMPORAL_RETENTION=72h` | confirmed |
| ADR-0007 asks new attempt write paths to take the fence or justify (SR:147) | ADR-0007:84-85 | confirmed |
| Design §4.4 quote "where supported and stable enough" (ADR:22-24) | `docs/roadmap/design-decisions.md`:32 | confirmed |
| Pinned temporalio source: `subscribe()` catches `TruncatedOffset` and restarts at 0 (SR:115-116, PR:13-15, NV:24-25) | `.venv/.../workflow_streams/_client.py`:603-608 `if cause_type == TRUNCATED_OFFSET_ERROR_TYPE: offset = 0; continue` | confirmed |
| NV: defaults `batch_interval` 2 s, `max_batch_size` None, `max_retry_duration` 600 s; `from_within_activity`; Signals, Updates and Queries; poll Update raises for a nonzero offset below the base; offsets start at 0; the stream registers its Signal handler; `publisher_id` random and not settable; no query returns the base; `continue_as_new` carries state; ~1 MB poll cap; "experimental" | `_client.py`:123-125, 158-159 (no constructor argument for it), 204; `_stream.py`:77, 86-89, 154, 159-162, 267, 289, 411-415, 474-475 (the offset query returns base + length, not the base), 58 `_MAX_POLL_RESPONSE_BYTES = 1_000_000` | confirmed |
| NV repository claims: DSH emits one `token` per response; `AttemptEvents` `seq` and `attempt_id`; `AgentEvent` frozen with extra forbidden; worker uses `NoOpSink`; `dsh_container.runner(sink)`; `package = false`; `spikes/` outside ruff, mypy and pytest; `dynamicconfig.yaml` empty; no Continue-As-New in production | `harness_activity/dsh/gateway.py`:12, 316-323; `harness_activity/events.py`:33-54; `common/schemas/base.py`:14-18; `workers/main.py`:97 with `runner.py`:227, 238; `tests/support/dsh_container.py`:112-115; `pyproject.toml`:25, 30, 42, 47; `infra/temporal/dynamicconfig.yaml` is `{}`; no `continue_as_new` outside `spikes/` | confirmed |
| `AgentEvent` copy matches the root fields; payloads hold no model text (SR:120-121) | field-list diff prints `same-fields`; `common/schemas/events.py`:36-38 comment; the fixture has 44 events with counts and tool names only | confirmed |
| PR probe descriptions | 1bfac67 `probes/jetstream_start_below_base.py` (20 messages, purge to 15, start 5), `streams_roll_over.py` (600 + 5 events), `streams_update_limit.py` | scripts match their descriptions; the observed outputs are unverifiable (U1) |

## Contradicted or unverifiable claims

| # | Severity | Location | Claim (quoted) | Evidence |
| --- | --- | --- | --- | --- |
| N1 | Nit (contradicted) | RM:7-8 | "ran one shared suite and two workloads against each" | NATS ran only the suite. SR:17 says "its load runs were not needed", and no `load-nats-*.json` exists in `results/` |
| N2 | Nit (contradicted, overgeneralised) | SR:123-124 | "A removal through the end of the log yields no expiry until a later event arrives (impl review F55), the same for every option." | F55 (`reviews.md`:92) says "**during a read**". A fresh read reports it: the memory probe printed `[Expired(retained_base=11)]`, and `table.py`:137-142 applies the same `expiry_for` check, setting `base` to `LEAST(offset, next_offset)` at 173 |
| N3 | Nit (inconsistent) | SR:117-119 against PR:15-16 | SR: "The spike meets R2 for every option with one reader rule (`transport.guarded()`)". PR: "Both options meet R2 in the spike only because the reader checks the retained base before reading" | Both mechanisms exist: `expiry_for` before reading (`table.py`:137-142; 1bfac67 `streams.py`:130-137, `jetstream.py`:78-85) and `guarded` during the read (`transport.py`:218-235). Neither statement alone is accurate; the base check is what covers N2's case |
| N4 | Nit (imprecise figure) | DL row (line 9) | "~20x less Temporal CPU" | 20.7x, 22.8x, 22.7x per run; 22.7x on medians. SR and ADR say "~20-23x" |
| N5 | Nit (contradicted) | ADR:46 | "~314 lines of workarounds (batch-ID dedup, expiry reporting, cancellation)" | 314 is the whole of `streams.py` (199) plus `streams_workflow.py` (115) at 1bfac67, including the plain transport; SR:139 correctly says "Spike code (whole files)" |
| N6 | Nit (imprecise) | ADR:72-73 | "with the spike's 4 publishers sharing it, 17 or more followers in one process would block them" | `max_size=20` (`table.py`:61): 17 followers leave 3 connections for 4 publishers, so publishers queue for a connection rather than block. All are blocked only at 20. `latest()` (`table.py`:161) also draws from the pool |
| N7 | Nit (imprecise) | ADR:74, SR:140 | "every follower wakes for every workflow's batch" | Every follower connection receives every `NOTIFY` on the single channel and runs its callback, but `table.py`:131-133 sets `woken` only when the payload matches the follower's own workflow, so other followers do not re-fetch |
| N8 | Nit (future stated as current) | ADR:84-86 | "The spike's shared suite ... and load runner ... run against the Phase 2 implementation behind the same interface" | Phase 2 has not started (AGENTS.md status); `factories.py`:37-40 registers only `memory` and `table` |
| N9 | Nit (future stated as current) | ADR:66-68, SR:134 | "the events share the application database's backups, access control and Kubernetes path"; "event writes can be fenced" | No backup mechanism exists yet (SR itself says "(Phase 3A)"). The fence is not implemented in the spike (`table.py`:70-104 takes no advisory lock); SR:151-152 says "not measured here" |
| N10 | Nit (future stated as current) | SR:135 | "the app role; scoping by workflow and tenant in queries" | The app role is confirmed (`praxismesh`, not a superuser). The spike schema has no tenant column (`table.py`:33-52; live `\d spike76.events` shows `workflow_id`, `offset`, `body`), so tenant scoping is planned, not built |
| N11 | Nit (inconsistent) | SR:52 heading | "Events published (offered: 60,232)" over the c1fda62 columns too | The closed-loop runner at c1fda62 had no fixed offered load: its rate depended on publish time (`load-c1fda62.py`:97-129). The caveat at SR:67-70 explains this; the heading does not |
| N12 | Nit (omission) | ADR:61 | "NATS JetStream passed the correctness suite" | It passed the 69c95c4 suite, which predates `check_r1_cancel` (added in 5ae0731). SR:36 discloses this; the ADR does not |
| N13 | Nit (inconsistent units) | NV:31 | "R5's 10% bound is therefore 5,120 events and 5 MB per run" | The code uses `50 * 1024 * 1024 * 0.1` = 5 MiB (`load.py`:53, 223), as SR:33 says ("5 MiB") |
| N14 | Nit (future stated as current) | SR:155-156 | "The hosting Workflow can refuse batches from an attempt older than the newest it has seen" | No such check exists in 1bfac67 `streams_workflow.py`:87-97 (dedup by batch ID only). It is phrased as a possibility, so this is a Nit |
| U1 | Nit (unverifiable) | PR:10, PR:12 | JetStream probe: "silently delivers from 15 (6 messages)"; roll-over probe: "`Expired(101)`, then offsets 101-605" | The probe outputs were never committed; NATS and Streams are gone at 8153e7b. The scripts at 1bfac67 are consistent (20 messages, purge to 15 leaves 15-20; 600 events keeping 500 gives base 101, and 5 more reach 605) |
| U2 | Nit (unverifiable) | SR:88, NV:128-129 | stall at the limit, server message "The limit on the total number of distinct updates in this workflow has been reached (2000)" | No log of the message is committed. The Update counts total exactly 2,000 per run, which is consistent |
| U3 | Nit (unverifiable) | SR:84 | "The 200 ms publish batch accounts for most of the latency of every option." | No latency breakdown was measured. It is consistent with mean latency of 96-113 ms against a mean batch wait of about 100 ms |
| U4 | Nit (unverifiable, hedged) | SR:100, NV:137 | rolled over "when Temporal suggested Continue-As-New, apparently on history size" | The runs rolled over at 191-207 batches, far below the 2,000-batch trigger, so the suggestion fired. The reason Temporal gave was not recorded |
| U5 | Nit (unverifiable) | SR:132, SR:135, SR:140, NV:7-47 | external facts: the NATS Helm chart's 3-replica StatefulSet; Temporal limits (50 MB, 51,200 events, 2 MB, warnings); "any Temporal client can query or update any Workflow"; PyPI and release dates; "~100 ms round trip"; JetStream documentation behaviour | These are documentation facts outside the system; not checked against live docs. The code constants agree (`load.py`:53-54) and the local Temporal has no auth configured (no auth or TLS keys in `infra/docker-compose.yml`) |
| U6 | Nit (unverifiable) | SR:153-156 | Streams fencing assessment | A design argument; nothing to observe |
