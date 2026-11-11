# PraxisMesh developer commands. The local stack is defined in
# infra/docker-compose.yml and configured by infra/.env (see infra/.env.example).

ENV_FILE ?= infra/.env
COMPOSE := docker compose --env-file $(ENV_FILE) -f infra/docker-compose.yml
# Long-running services; the one-shot jobs are checked separately.
SERVICES := db temporal temporal-ui s3
JOBS := temporal-schema temporal-namespace

# Load infra/.env into make (and into the tests' environment) when it exists.
ifneq (,$(wildcard $(ENV_FILE)))
include $(ENV_FILE)
export
endif

.PHONY: help check up down reset status migrate smoke restart-check logs

help:
	@echo "make up            start the stack and wait until it is healthy"
	@echo "make down          stop the stack (keeps data)"
	@echo "make reset         stop the stack and delete its data volumes"
	@echo "make status        show service health and the model endpoint"
	@echo "make migrate       apply application database migrations"
	@echo "make smoke         run the integration tests against the stack"
	@echo "make restart-check check that state survives a restart"
	@echo "make logs          follow the stack's logs"

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
	@$(COMPOSE) up -d temporal-namespace >/dev/null 2>&1
	@for job in $(JOBS); do \
		id=$$($(COMPOSE) ps -aq $$job); \
		code=$$([ -n "$$id" ] && docker wait $$id); \
		if [ "$$code" != "0" ]; then echo "error: job $$job exited with '$$code'; see: make logs" >&2; exit 1; fi; \
	done
	@echo "stack is up: Temporal 127.0.0.1:$(TEMPORAL_PORT), UI http://127.0.0.1:$(TEMPORAL_UI_PORT), S3 http://127.0.0.1:$(S3_PORT), DB 127.0.0.1:$(DB_PORT)"

down: check
	@$(COMPOSE) down

reset: check
	@$(COMPOSE) down --volumes --remove-orphans

status: check
	@$(COMPOSE) ps -a --format 'table {{.Service}}\t{{.Status}}'
	@bad=""; for s in $(SERVICES); do \
		h=$$($(COMPOSE) ps --format '{{.Health}}' $$s 2>/dev/null); \
		[ "$$h" = "healthy" ] || bad="$$bad $$s"; \
	done; \
	if [ -n "$$bad" ]; then echo "unhealthy or stopped:$$bad"; else echo "all services healthy"; fi
	@if [ -z "$(VLLM_BASE_URL)" ]; then \
		echo "model endpoint: not configured (VLLM_BASE_URL is empty)"; \
	elif curl -fsS -m 5 -o /dev/null "$(VLLM_BASE_URL)/v1/models"; then \
		echo "model endpoint: $(VLLM_BASE_URL) answers /v1/models"; \
	else \
		echo "model endpoint: $(VLLM_BASE_URL) is unreachable"; \
	fi

migrate: check
	@uv run alembic -c common/persistence/alembic.ini upgrade head

smoke: check
	@uv run pytest -m integration tests/integration

restart-check: check
	@uv run python -m tests.integration.restart_check

logs: check
	@$(COMPOSE) logs -f --tail 100
