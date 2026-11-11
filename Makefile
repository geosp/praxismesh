# PraxisMesh developer commands. The local stack is defined in
# infra/docker-compose.yml and configured by infra/.env (see infra/.env.example).
#
# Make never reads infra/.env itself. Docker Compose reads it with --env-file
# (including COMPOSE_PROJECT_NAME), and the tests and migrations get it through
# `uv run --env-file`. infra/check-prereqs.sh keeps it to a syntax both read the
# same way. A variable set in your shell overrides the file for both.

ENV_FILE ?= infra/.env
export ENV_FILE
COMPOSE := docker compose --env-file $(ENV_FILE) -f infra/docker-compose.yml
UV := uv run --env-file $(ENV_FILE)
# Long-running services; the one-shot jobs are checked separately.
SERVICES := db temporal temporal-ui s3
JOBS := temporal-schema temporal-namespace
JOB_TIMEOUT := 120

.PHONY: help check up down reset status migrate smoke restart-check unhealthy-check logs

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

check:
	@sh infra/check-prereqs.sh $(ENV_FILE)

# down and reset need only the project name (from the shell, else infra/.env),
# so they still run when other settings are invalid. Without a valid name they
# refuse rather than guess, so they never act on another checkout's stack.
PROJECT = $$(sh infra/check-prereqs.sh --project-only $(ENV_FILE))

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

down:
	@name=$(PROJECT) && docker compose -p "$$name" down

reset:
	@name=$(PROJECT) && echo "deleting the stack and data volumes of project $$name" && \
		docker compose -p "$$name" down --volumes --remove-orphans

status: check
	@$(UV) python -m tests.support.status

migrate: check
	@$(UV) alembic -c common/persistence/alembic.ini upgrade head

smoke: check
	@$(UV) pytest -m integration tests/integration

restart-check: check
	@$(UV) python -m tests.integration.restart_check

unhealthy-check: check
	@$(UV) python -m tests.integration.unhealthy_check

logs: check
	@$(COMPOSE) logs -f --tail 100
