# Demo evidence: DSH migration phase 01 (harness seam and registry)

- Code: `4969d4dbeaddd6fd8f6af777a9b0fdbe50db0bb3`; docs: `38e379ce6849e315e3f4a779bf1ef08d1cbb060a`; date 2026-11-15.
- Environment: Linux x86_64 (Fedora, cgroup v2, SELinux enforcing), Docker, Python 3.11 via uv; disposable Compose project with its own ports; no model endpoint.
- Run by fresh verifier subagents in a disposable worktree ([raw reports](../reviews/general-dsh-production-harness/raw/)).

| Item | Command | Expected | Observed | Result |
|---|---|---|---|---|
| Isolation probe (with `SYS_ADMIN`) | header command of `infra/dsh/isolation-probe.sh` | freeze and kill a process tree | members=3, frozen=1, alive=0 of 3; SIGSTOP 3 of 3; user-namespace check fails as recorded | pass |
| Failure case: no `SYS_ADMIN` | same, default caps | named failure, SIGSTOP fallback | "remount refused", "cgroup root not writable"; SIGSTOP 3 of 3 | pass |
| Stale attempt fenced | integration suites | stale writes rejected | 33 passed, including concurrent start, refusal and Activity-level cases | pass |
| Registry rules | registry tests and edited copies | unknown or mismatched harness fails at load | errors quoted in the verification report | pass |
| dsh worker refused | `workers.main template local-dsh` | refuse | `CapabilityError ... cannot run yet` | pass |
| Regression | `make smoke`, `make recovery-check`, `make workers-check` | pass | 92 passed (4 skipped), 5 passed, task succeeded | pass |

Cleanup: `make workers-down` and `make reset` for the disposable project; worktree removed.
The user's running stack was not touched.
