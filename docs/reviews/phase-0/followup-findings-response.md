# Phase 0 targeted follow-up: response to findings

Response to the [implementation review follow-up](implementation-review-followup.md) (FAIL) and the [verification follow-up](verification-followup.md) (fail) of `61c40ef`. Those reports are unchanged. The fixes are on branch `fix/34-phase-0-followup-findings` (issue #34) for a final narrow follow-up. Its scope, agreed with the owner, is R1-R3, VF1-VF2, R4/VF3 and R5/VF10.

## Majors

| ID | Resolution |
|---|---|
| R1 / VF2 | **Fixed.** `make down` and `make reset` take the project name from the shell, or else from `infra/.env` (`check-prereqs.sh --project-only`). They run `docker compose -p <name> down`, and **refuse** when no valid name is set, with no fallback to `praxismesh`. A name set in the shell now wins over the file, for Compose too. Tests: `test_reset_refuses_without_project_name`, `test_shell_project_name_wins`, `test_bad_project_name_rejected` (empty, uppercase, space). Overview claims corrected. |
| R2 / VF1 | **Fixed at the root.** Make no longer reads `infra/.env` (no `include`). Compose reads it with `--env-file`; tests, migrations and `make status` get it through `uv run --env-file`, which does not continue comments and lets the shell win, as Compose does. The check also rejects any line ending in `\`, unknown keys (`MAKEFLAGS`, `SHELL`, `ENV_FILE`, typos), and values outside `A-Z a-z 0-9 . _ : / @ % + , = -`. Tests run through `make up` and assert the line number: `test_comment_continuation_rejected`, `test_unknown_key_rejected`, `test_value_character_rejected` (12 characters, one each). |
| R3 | **Fixed.** `make restart-check` runs `make up` with `TEMPORAL_RETENTION=96h` from the shell, requires the namespace to show 96h, then runs `make up` again and requires the configured retention back. |

## Nits in scope

| ID | Resolution |
|---|---|
| R4 / VF3 | Fixed: CI's failure step runs `make status \|\| true` before printing the logs. |
| R5 / VF10 | Fixed: the health check accepts the marker on `postgres` or, for volumes created before PR #38, on `praxismesh`. Observed: a volume with only the old marker became healthy after its container was recreated. README notes that no reset is needed. |

## Other Nits

| ID | Resolution |
|---|---|
| R6 | Fixed: the unhealthy check runs `make smoke` (not one test) and fails if `db` or `make up` do not come back. |
| R7 | Fixed: the snapshot is also compared after `compose stop` plus `make up`, and the namespace job's log must show it ran without updating. `DescribeNamespaceResponse` in this API version has no config version to compare. |
| R8 / VF7 | Fixed: `namespace.sh` treats only "is not found" as absent and retries other `describe` errors for 30 s before failing with the error. `make up` prints a failed job's last 10 log lines. Observed with a `1s` retention: the server's own message is shown. |
| R9 | Fixed: `COMPOSE_PROJECT_NAME` must match `^[a-z0-9][a-z0-9_-]*$` and is required. Renaming a project still leaves the old one's containers and volumes; the README's "Several checkouts" covers naming. |
| R10 / VF8 | Fixed: Make no longer parses `infra/.env`. |
| R11 | Fixed by the value character set; sourcing the file in a shell is now safe. |
| R12 | Fixed: best-effort cleanup suppresses any exception. |
| R13 | Fixed: `make up` polls the job's state for up to 120 s with no GNU `timeout`, and reports a missing container separately. |
| R14 | Fixed: retention must be at least one day and at most five digits. |
| R15 | Fixed: 60 s Workflow execution timeout, longer than 3 attempts of 10 s plus backoff. |
| R16 | Fixed: tasks 1.4 and 6.1 annotated; an amendment note at the top of the RFC; a note in ADR-0002 about `0002`; the `init.sh` comment and the overview corrected; the demo's `stop db` command no longer hard-codes a project. |
| R17 | Fixed: syntax tests run `make up`, assert the line number, and cover each rejected character separately. |
| R18 / VF9 | Fixed: the README's curl commands send `Authorization: Bearer $VLLM_API_KEY`. |
| R19 / VF11 | Fixed: `CONNECT` on `paradedb` is revoked from `PUBLIC`; observed refused for both roles. |
| VF4 | Fixed: the overview says `make status` makes `make` exit non-zero (2). |
| VF5 | Fixed with R16. |
| VF6 | Accepted (the figures are dated observations). |
| VF12 | Fixed: the overview names `61c40ef` and this branch; verify the merge commit. |
