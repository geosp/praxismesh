# PraxisMesh developer commands. The local stack is defined in
# infra/docker-compose.yml and configured by infra/.env (see infra/.env.example).
#
# Make never reads infra/.env itself. Docker Compose reads it with --env-file
# (including COMPOSE_PROJECT_NAME), and the tests and migrations get it through
# `uv run --env-file`. infra/check-prereqs.sh keeps it to a syntax both read the
# same way. Other variables set in your shell override the file for both, but the
# project name never does (below).

# `make <target> ENV_FILE=...` selects another env file; an ENV_FILE exported in
# the shell is ignored, like COMPOSE_PROJECT_NAME.
ENV_FILE := infra/.env
export ENV_FILE

# The Compose project name comes only from this checkout's env file. A value in
# the shell (for example from sourcing another checkout's infra/.env) is
# replaced for every command make runs, so no target can act on another
# checkout's stack. Without a valid name, every target refuses.
PROJECT_NAME := $(shell sh infra/check-prereqs.sh --project-only $(ENV_FILE) 2>/dev/null)
ifneq ($(PROJECT_NAME),)
export COMPOSE_PROJECT_NAME := $(PROJECT_NAME)
else
unexport COMPOSE_PROJECT_NAME
endif
COMPOSE := docker compose -p "$(PROJECT_NAME)" --env-file $(ENV_FILE) -f infra/docker-compose.yml
# Prints why there is no project name, then fails.
REQUIRE_PROJECT := [ -n "$(PROJECT_NAME)" ] || { sh infra/check-prereqs.sh --project-only $(ENV_FILE) >/dev/null; exit 1; }
UV := uv run --env-file $(ENV_FILE)
# Long-running services; the one-shot jobs are checked separately.
SERVICES := db temporal temporal-ui s3
JOBS := temporal-schema temporal-namespace
JOB_TIMEOUT := 120

.PHONY: help check up down reset status migrate smoke restart-check unhealthy-check logs registry-lock workers-up workers-down workers-check recovery-check benchmark observability-up observability-down demo-worker-loss task task-status task-output

help:
	@echo "make up              start the stack and wait until it is healthy"
	@echo "make down            stop the stack (keeps data)"
	@echo "make reset           stop the stack and delete its data volumes"
	@echo "make status          show service health and the model endpoint (fails if unhealthy)"
	@echo "make migrate         apply application database migrations"
	@echo "make smoke           run the integration tests against the stack"
	@echo "make restart-check   check repeat starts, a retention change and a restart"
	@echo "make unhealthy-check check that a stopped database is reported by name"
	@echo "make logs            follow the stack's logs"
	@echo "make registry-lock   record new template versions in registry/registry.lock"
	@echo "make workers-up      build and start the orchestrator and two template workers"
	@echo "make workers-down    stop the workers"
	@echo "make workers-check   run a scripted task through the worker containers (fake model)"
	@echo "make recovery-check  kill the worker running a task; the other must finish it (fake model)"
	@echo "make benchmark       run the agent benchmark on the real model (ARGS=--baseline to record it)"
	@echo "make observability-up   start Prometheus (127.0.0.1:9090) and Jaeger (127.0.0.1:16686)"
	@echo "make task PROMPT=... [OUTPUT=path]  submit a task and wait for its result"
	@echo "make task-status ID=...             show a task: attempts, latest checkpoint, orders"
	@echo "make demo-worker-loss               kill the worker container running a task (demo step 2)"
	@echo "make task-output ID=... FILE=...    print one of a task's output files"

check:
	@sh infra/check-prereqs.sh $(ENV_FILE)

# `docker compose up --wait` reports a one-shot job that exited 0 as a failure,
# so wait on the long-running services, then run the namespace job and check
# both jobs' exit codes.
up: check
	@$(COMPOSE) up -d --wait --wait-timeout 180 $(SERVICES) || { \
		echo "error: the stack did not become healthy; see the service named above, 'make status' and 'make logs'." >&2; \
		echo "       On a first start, a failed database init needs 'make reset' (this deletes all data)." >&2; \
		exit 1; }
	@$(COMPOSE) up -d temporal-namespace >/dev/null || { \
		echo "error: could not start job temporal-namespace; see the message above" >&2; exit 1; }
	@for job in $(JOBS); do \
		id=$$($(COMPOSE) ps -aq $$job); \
		if [ -z "$$id" ]; then echo "error: job $$job has no container" >&2; exit 1; fi; \
		waited=0; \
		while [ "$$(docker inspect -f '{{.State.Status}}' $$id)" != "exited" ]; do \
			if [ $$waited -ge $(JOB_TIMEOUT) ]; then echo "error: job $$job did not finish within $(JOB_TIMEOUT) s" >&2; exit 1; fi; \
			sleep 1; waited=$$((waited + 1)); \
		done; \
		code=$$(docker inspect -f '{{.State.ExitCode}}' $$id); \
		if [ "$$code" != "0" ]; then \
			echo "error: job $$job exited with $$code; its last log lines:" >&2; \
			$(COMPOSE) logs --no-log-prefix --tail 10 $$job >&2; exit 1; \
		fi; \
	done
	@echo "stack is up; run 'make status' for addresses and health"

# down and reset need only the project name, so they still run when other
# settings are invalid.
down:
	@$(REQUIRE_PROJECT)
	@docker compose -p "$(PROJECT_NAME)" down

reset:
	@$(REQUIRE_PROJECT)
	@echo "deleting the stack and data volumes of project $(PROJECT_NAME)"
	@docker compose -p "$(PROJECT_NAME)" down --volumes --remove-orphans

status: check
	@$(UV) python -m tests.support.status

migrate: check
	@$(UV) alembic -c common/persistence/alembic.ini upgrade head

smoke: check
	@$(UV) pytest -m integration tests/integration --ignore=tests/integration/test_recovery.py

restart-check: check
	@$(UV) python -m tests.integration.restart_check

unhealthy-check: check
	@$(UV) python -m tests.integration.unhealthy_check

logs: check
	@$(COMPOSE) logs -f --tail 100

# Record new template versions; existing entries are never rewritten.
registry-lock:
	@uv run python -m registry.lock

WORKERS := orchestrator worker-a worker-b

workers-up: check
	@$(COMPOSE) --profile workers up -d --build --wait --wait-timeout 180 $(WORKERS)

# A scripted task through the worker containers, against the deterministic fake
# model (CI). Afterwards the workers still point at the fake model: run
# `make workers-up` to point them back at VLLM_BASE_URL.
workers-check: check
	@VLLM_BASE_URL=http://fake-model:8765 $(COMPOSE) --profile workers --profile fake-model \
		up -d --build --wait --wait-timeout 180 fake-model $(WORKERS)
	@$(MAKE) --no-print-directory task \
		PROMPT="Order 3 units of SKU-1 and write order-summary.md." OUTPUT=order-summary.md

# Workers as host processes, one SIGKILLed mid-task: recovery after edits, no
# repeated side effect, checkpoint positions (RFC: Recovery check).
recovery-check: check
	@$(UV) pytest -m integration tests/integration/test_recovery.py -v

# The agent benchmark on the real model (not in CI; plan §8).
benchmark: check
	@$(UV) python -m tests.benchmarks.run $(ARGS)

observability-up: check
	@$(COMPOSE) --profile observability up -d prometheus jaeger

observability-down: check
	@$(COMPOSE) --profile observability rm -sf prometheus jaeger

workers-down: check
	@$(COMPOSE) --profile workers --profile fake-model rm -sf $(WORKERS) fake-model

task: check
	@test -n "$(PROMPT)" || { echo "error: set PROMPT=..." >&2; exit 1; }
	@$(UV) python -m orchestrator.cli task submit --wait --instructions "$(PROMPT)" \
		$(if $(OUTPUT),--output $(OUTPUT)) $(if $(PROFILE),--profile $(PROFILE))

task-status: check
	@$(UV) python -m orchestrator.cli task status $(ID)

demo-worker-loss: check
	@sh infra/demo/worker-loss.sh

task-output: check
	@$(UV) python -m orchestrator.cli task output $(ID) $(FILE)
