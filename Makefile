# PraxisMesh developer commands. The local stack is defined in
# infra/docker-compose.yml and configured by infra/.env (see infra/.env.example).

ENV_FILE ?= infra/.env

# Load infra/.env into make (and into the tests' environment) when it exists.
# check-prereqs.sh keeps it to plain KEY=value lines, which Make and Compose
# read the same way.
ifneq (,$(wildcard $(ENV_FILE)))
include $(ENV_FILE)
export
endif

# Each checkout that runs its own stack needs its own project name, or its
# `make reset` deletes another checkout's data. Set it in infra/.env.
COMPOSE_PROJECT_NAME ?= praxismesh
export COMPOSE_PROJECT_NAME
COMPOSE := docker compose -p $(COMPOSE_PROJECT_NAME) --env-file $(ENV_FILE) -f infra/docker-compose.yml
# down and reset work by project name alone, so they still run with a missing
# or broken infra/.env.
COMPOSE_BY_NAME := docker compose -p $(COMPOSE_PROJECT_NAME)
# Long-running services; the one-shot jobs are checked separately.
SERVICES := db temporal temporal-ui s3
JOBS := temporal-schema temporal-namespace
JOB_TIMEOUT := 120

.PHONY: help check up down reset status migrate smoke restart-check unhealthy-check logs

help:
	@echo "make up              start the stack and wait until it is healthy"
	@echo "make down            stop the stack (keeps data)"
	@echo "make reset           stop the stack and delete its data volumes"
	@echo "make status          show service health and the model endpoint (exit 1 if unhealthy)"
	@echo "make migrate         apply application database migrations"
	@echo "make smoke           run the integration tests against the stack"
	@echo "make restart-check   check that state survives a restart and a repeat start"
	@echo "make unhealthy-check check that a stopped database is reported by name"
	@echo "make logs            follow the stack's logs"

check:
	@sh infra/check-prereqs.sh $(ENV_FILE)

# `docker compose up --wait` reports a one-shot job that exited 0 as a failure,
# so wait on the long-running services, then run the namespace job and check
# both jobs' exit codes.
up: check
	@$(COMPOSE) up -d --wait --wait-timeout 180 $(SERVICES) || { \
		echo "error: the stack did not become healthy; run 'make status' and 'make logs'." >&2; \
		echo "       If database init failed or its passwords changed, run 'make reset'." >&2; \
		exit 1; }
	@$(COMPOSE) up -d temporal-namespace >/dev/null || { \
		echo "error: could not start job temporal-namespace; see the message above" >&2; exit 1; }
	@for job in $(JOBS); do \
		id=$$($(COMPOSE) ps -aq $$job); \
		code=$$([ -n "$$id" ] && timeout $(JOB_TIMEOUT) docker wait $$id); \
		if [ -z "$$code" ]; then echo "error: job $$job did not finish within $(JOB_TIMEOUT) s; see: make logs" >&2; exit 1; fi; \
		if [ "$$code" != "0" ]; then echo "error: job $$job exited with $$code; see: make logs" >&2; exit 1; fi; \
	done
	@echo "stack is up: Temporal 127.0.0.1:$(TEMPORAL_PORT), UI http://127.0.0.1:$(TEMPORAL_UI_PORT), S3 http://127.0.0.1:$(S3_PORT), DB 127.0.0.1:$(DB_PORT)"

down:
	@$(COMPOSE_BY_NAME) down

reset:
	@$(COMPOSE_BY_NAME) down --volumes --remove-orphans

status: check
	@$(COMPOSE) ps -a --format 'table {{.Service}}\t{{.Status}}'
	@if [ -z "$(VLLM_BASE_URL)" ]; then \
		echo "model endpoint: not configured (VLLM_BASE_URL is empty)"; \
	elif curl -fsS -m 5 -o /dev/null $(if $(VLLM_API_KEY),-H "Authorization: Bearer $(VLLM_API_KEY)") "$(VLLM_BASE_URL)/v1/models"; then \
		echo "model endpoint: $(VLLM_BASE_URL) answers /v1/models"; \
	else \
		echo "model endpoint: $(VLLM_BASE_URL) is unreachable"; \
	fi
	@bad=""; for s in $(SERVICES); do \
		h=$$($(COMPOSE) ps --format '{{.Health}}' $$s 2>/dev/null); \
		[ "$$h" = "healthy" ] || bad="$$bad $$s"; \
	done; \
	if [ -n "$$bad" ]; then echo "unhealthy or stopped:$$bad"; exit 1; fi; \
	echo "all services healthy"

migrate: check
	@uv run alembic -c common/persistence/alembic.ini upgrade head

smoke: check
	@uv run pytest -m integration tests/integration

restart-check: check
	@uv run python -m tests.integration.restart_check

unhealthy-check: check
	@uv run python -m tests.integration.unhealthy_check

logs: check
	@$(COMPOSE) logs -f --tail 100
