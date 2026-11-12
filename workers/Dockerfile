# The generic PraxisMesh worker image (RFC Phase 1: Workers and Compose).
# Built on the installer's machine by `make workers-up`; never published.
# It contains no harness CLI: the Claude Agent SDK runner is deferred.
FROM python:3.11-slim-bookworm@sha256:a83ba18aef0f865b1a4a611c2cf460fe446f2795673bbb9fe43be570439e3b39

COPY --from=ghcr.io/astral-sh/uv:0.13.5@sha256:32a7bb39b496babbd997b0a39a4d66c126bdaf5661b302bf6f06abda8deca6ff /uv /usr/local/bin/uv

# Programs the local-default template's run_command may start (cli_tools).
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 10001 praxis
WORKDIR /app
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH=/app/.venv/bin:$PATH PRAXIS_SCRATCH=/scratch

COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-dev --no-install-project
COPY common common
COPY registry registry
COPY orchestrator orchestrator
COPY harness_activity harness_activity
COPY sample_mcp sample_mcp
COPY workers workers
COPY tests/support tests/support
RUN mkdir -p /scratch && chown praxis /scratch

USER praxis
ENTRYPOINT ["python", "-m", "workers.main"]
