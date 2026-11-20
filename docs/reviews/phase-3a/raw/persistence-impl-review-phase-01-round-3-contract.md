Review of 619593b..56c0170 for phase 01 of the Phase 3A persistence plan, contract lens.

I found no Blocker or Major findings, and three Nits.

**What the diff is.** It touches two files:
- `/home/geo/develop/praxismesh/common/persistence/migrations/env.py:22-24` now calls `fileConfig(config.config_file_name, disable_existing_loggers=False)`.
- `/home/geo/develop/praxismesh/tests/integration/test_migration_0007.py:249-256` adds the regression test `test_an_in_process_migration_keeps_existing_loggers`.

It fixes F1 from the verifier's acceptance re-run (`/home/geo/develop/praxismesh/docs/reviews/phase-3a/raw/persistence-verification-phase-01-acceptance-rerun.md`). In the full `-m integration` run, `test_refusals_are_logged_with_ids[dsh]` failed with `KeyError: 'refused tool call'`, but it passed 10/10 on its own.

**1. Promises (R1, R2, R4, R5, R14, R18, R19, R20 and D1-D12).**
- The diff adds or changes no code that enforces any of these, and it does not weaken any of them.
- It is a test-isolation fix that makes the full integration suite pass, which is the phase's verification gate.
- No Given/When/Then scenario is affected. `env.py` still builds the URL and runs migrations exactly as before; only the logging setup changed.

**2. Universal claim in the change.** The comment says an in-process migration "must not silence the app's" loggers. There is only one `fileConfig` call in the repository (`env.py:24`), so every Alembic run goes through it:
- `make migrate` uses the CLI, where the flag has no practical effect.
- Running in-process happens only through `tests/support/scratch_db.py:27-32` (`migrate`). It is used by `test_migration_0007.py` and `tests/integration/test_refs.py`.
- No app code runs `command.upgrade` or `command.downgrade`; grep found only `scratch_db.py:30`.

So no place is missed for the "disabled" behaviour. The claim is only partly kept, though; see Nit 1.

**3. Observability.**
- The new test would fail without the fix. `alembic.ini` lists only the root, `sqlalchemy.engine` and `alembic` loggers. `praxis.harness` is not one of them and not a child of the last two. It already exists as a real Logger, created by `getLogger` at line 254 and by `harness_activity/*.py`, so the old `fileConfig` would set `disabled=True`.
- CI runs `make smoke`, which includes `tests/integration`, so CI now guards this regression. It still does not run the original failing test (`tests/test_runner_conformance.py`, F2 in the verifier report). That gap was there before this diff.

**4. Reuse and placement.**
- The diff adds one test function and no new helpers.
- It reuses the file's existing `scratch` fixture (`test_migration_0007.py:31-34`) and `tests/support/scratch_db.migrate`, with no duplication.

**Nits**
1. `env.py:24` / D-none (task: verification fix): `fileConfig` still removes every root handler and installs its own stderr `StreamHandler` with the root level at WARNING (`alembic.ini` `[logger_root]`/`[handler_console]`). After any in-process migration, the rest of the pytest session keeps that extra stderr handler. A handler set by `configure_logging` (`common/observability/logging.py:70-76`) would also be replaced, so "must not silence the app's" holds for `disabled`, but not for root handlers. I have not verified that any current test breaks from this. A test that checks stderr with `capsys` after a migration in the same session (for example in the style of `tests/test_cli.py:43`) could pick up `WARNI [...]` lines. One fix is for `migrate` in `scratch_db.py` to set `config.config_file_name`-free attributes or skip `fileConfig` when running in-process, for example `if config.config_file_name is not None and not config.attributes.get("database")`.
2. `test_migration_0007.py:249-256`: the test only checks `praxis.harness.disabled`. It does not check that a WARNING from that logger still reaches `caplog` after a migration, which is the behaviour that actually failed. An assert that `caplog` captures a `praxis.harness` warning logged after `migrate` would cover root-handler or propagation side effects as well. I rated this a Nit because the root cause found was `disabled`.
3. Placement: the new test is about `env.py`'s logging, which applies to every revision, but it sits in the file for migration 0007. `tests/integration/test_database.py` is the general home for migration tests ("migrations at head"). The test also calls `migrate(..., "0007")`, which runs the 0007 backfill without needing to. If someone later moves or trims the 0007 tests, this check could be lost with them. I rated it a Nit because it causes no functional problem.
