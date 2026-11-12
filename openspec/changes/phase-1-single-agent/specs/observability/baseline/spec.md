# Spec Delta

## Purpose

The observability every later phase builds on: structured logs with context IDs, distributed traces from submission to Activity, worker metrics, and an optional local Prometheus and trace viewer (plan Phase 1 task 4, rev 2.10).

## ADDED Requirements

### Requirement: Logs carry context IDs
Workers and the CLI SHALL log JSON lines that carry, where known, the request, task, workflow, turn and attempt IDs and the worker identity. (Plan: Phase 1 task 4.)

#### Scenario: Harness log line
- **WHEN** a harness turn logs a tool call
- **THEN** the line is valid JSON and includes `task_id`, `workflow_id`, `turn` and `attempt`

### Requirement: One trace per task
A task SHALL produce one trace whose spans cover the CLI submission, the Workflow, each Activity, and the harness's model and tool calls, using Temporal's OpenTelemetry interceptor. Export SHALL be OTLP when configured and off otherwise. (Plan: Phase 1 task 4 and accept criterion "one trace follows a task from submission to result".)

#### Scenario: Trace parentage
- **WHEN** a scripted task runs with an in-memory span exporter
- **THEN** every Activity, model and tool span descends from the submission span

### Requirement: Worker metrics
Each worker SHALL expose Prometheus metrics: Activity duration, heartbeat lag, tokens, tool calls and errors, and checkpoint size and time. An optional Compose profile SHALL run Prometheus and a trace viewer. (Plan: Phase 1 task 4.)

#### Scenario: Metrics after a task
- **WHEN** a task has completed on a worker
- **THEN** its `/metrics` endpoint reports a non-zero Activity count and token count
