# Phase 0 final follow-up: response to findings

Response to the [implementation review follow-up 2](implementation-review-followup-2.md) (FAIL) and the [verification follow-up 2](verification-followup-2.md) (fail) of `f0337f1`. Those reports are unchanged. The fixes are on branch `fix/34-phase-0-final-fixes` (issue #34).

## Majors

| ID | Resolution |
|---|---|
| N1 / VG2 | **Fixed.** The project name comes only from the env file. `check-prereqs.sh --project-only` ignores the shell. The Makefile resolves the name once, passes it to every Compose call with `-p`, and exports it to every command it runs (uv, the tests, nested `make`), replacing any shell value. An `ENV_FILE` exported in the shell is ignored too; select another file only with `make <target> ENV_FILE=…`. The README's by-hand snippet now runs in a throwaway shell. Tests: `test_shell_project_name_ignored` (up, down, reset, logs with `COMPOSE_PROJECT_NAME=other` in the environment) and `test_up_and_reset_resolve_the_same_project`. |
| N2 / VG1 | **Fixed.** A repeated key is rejected, naming the line of the repeat. Test: `test_duplicate_key_rejected`. |

## Nits

| ID | Resolution |
|---|---|
| N3 / VG3 | Fixed with N1: an empty or set shell value is replaced by the file's value. |
| N4 | Accepted: other shell overrides win by design (documented in the README) and fail closed at the server. |
| N5 | Fixed: an `ENV_FILE` exported in the shell is ignored (`ENV_FILE :=`); only the command line selects another file. |
| N6 | Fixed: the env tests run with `DOCKER_HOST` pointing at a non-existent socket, so a regression cannot touch a real stack. |
| N7 | Fixed: `test_up_and_reset_resolve_the_same_project` compares the `-p` that `make -n up` and `make -n reset` would pass. |
| N8 | Fixed: the Compose file comment describes the current behavior. |
| N9 | (a) Fixed: the restart check picks 96h, or 120h when 96h is configured, so an update always happens. (b) The failure branch was observed by hand (`TEMPORAL_RETENTION=1s make up` prints the server's error) and is not automated. (c) Accepted: shell and file values are equivalent for Compose. |
| N10 | Fixed: the old marker on `praxismesh` is no longer trusted. An unmarked volume counts as initialised only if `praxismesh` has both `vector` and `pg_search`, which init creates together as its last step. `vector` requires the superuser, so the app role cannot fake this. Observed: with both extensions dropped, the health check stays failing. |
| N11 / VG4 | Fixed: such a volume is upgraded once by the health check (the `REVOKE CONNECT` statements on `postgres`, `paradedb` and the three PraxisMesh databases, then the marker). Observed: `CONNECT` granted to `PUBLIC` on `postgres` and `paradedb` was revoked and the volume became healthy. README updated. |
| N12 | Accepted: R4 (the CI step) and R5 (the upgrade path) were observed by hand; R5's upgrade logic is now exercised by the observation above. |
| VG5 | Fixed: the unhealthy check prints the line `make status` reported and the line in which `make smoke` named the database. |
