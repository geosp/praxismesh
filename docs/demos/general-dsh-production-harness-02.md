# Demo evidence: DSH migration phase 02 (DSH runner and worker pair)

- Code: `86cfec87bfb1ed83c60150d2104a41b6720b7018` (first demo pass at `62ffc76`, same runtime code); docs: `7b06ce60046f59817c65b97db783fddd6d8f0d95`; date 2026-11-16.
- Environment: Linux x86_64 (Fedora, cgroup v2, SELinux enforcing), Docker with the containerd snapshotter, Python 3.11 via uv; disposable Compose project `pmverify02` with its own ports; fake model (`fake-model` Compose profile) as the endpoint.
- Run by fresh verifier subagents in disposable worktrees ([raw reports](../reviews/general-dsh-production-harness/raw/)).

| Item (phase 02 task) | Command | Expected | Observed | Result |
|---|---|---|---|---|
| 1.1 isolation probe | probe header flags in the DSH image | all checks pass | "lines=13 ok=13", `command_userns_blocked` ok | pass |
| 1.1 pin refusal | `tests/test_worker_runner.py` | refuse a launcher whose digest differs | refusal tests passed | pass |
| 1.2 pair, no network or credentials | `docker compose ... --profile dsh up -d dsh-a worker-dsh-a` (with `VLLM_BASE_URL=http://fake-model:8765`) | both up; DSH container isolated | `NetworkMode=none ReadOnly=true CapAdd=[CAP_SYS_ADMIN] Cgroupns=private`; interfaces `['lo']`; no credentials in env | pass |
| 1.3 runner choice | Temporal pollers; runner unit tests | `tpl.local-dsh` served by a DSH worker | `tpl.local-dsh ['…@1/local-dsh']`; tests passed | pass |
| End-to-end DSH task | `make task PROFILE=dsh PROMPT="Order 3 units of SKU-1 and write order-summary.md." OUTPUT=order-summary.md` | succeeds on DSH | `"status": "succeeded"`, `"template": "local-dsh"`, `"attempts": 1`, `"usage_known": true`; orders `[{"sku": "SKU-1", "qty": 3}]`; no attempt tree or cgroup left | pass |
| 2.1 migration | `alembic downgrade 0003`, `make migrate` on a populated DB | 0004 applies, rows kept | "0003 -> 0004", counts unchanged, `usage_ledger` exists | pass |
| 2.3 / 2.4 conformance | `pytest -m integration tests/test_runner_conformance.py` | dsh passes | 19 passed | pass |
| 2.5 integration (R5-R15, R18) | `make smoke` | pass without a model endpoint | 150 passed, 4 skipped (live-model tests) | pass (fail at 62ffc76, fixed) |
| Failure case: unreachable launcher | stop `dsh-a`, restart the worker | worker refuses | `CapabilityError: template local-dsh@1: the DSH launcher is not answering` | pass |
| Failure case: pin mismatch at start | `dsh-a` with a tampered `driver.py` | worker refuses | "DSH runtime sha256:d03ed7b6… does not match the registry lock sha256:a842ed2e…" | pass |
| Failure case: pin mismatch during a turn | swap in the tampered launcher, submit a DSH task | uncounted refusal, worker stops | "worker cannot serve its queue", exit 3; row `refused / dsh_unserviceable` | pass |
| Recovery | restore the real launcher | the task completes, refusal used no attempt | `succeeded`, `"attempts": 1`; rows `refused`, then `done` | pass |

Cleanup: `make reset` for the disposable project; worktrees removed. The owner's running stack was
not stopped. The verifier's build retagged the shared `praxismesh-worker:dev` and
`praxismesh-dsh:dev` tags; the owner's next `make workers-up` rebuilds them.
