# quality/agent-benchmarks Specification

## Purpose

A fixed suite of representative agent tasks with deterministic checks, run whenever a model, template, harness version or system prompt changes and at every phase closure, compared with a recorded baseline (plan Phase 1 task 5, §8 benchmark rule).

## Requirements

### Requirement: Benchmark suite and recorded results
`tests/benchmarks/agent_tasks/` SHALL hold at least 10 tasks, seeded from the Pre-0 spike, each with a deterministic pass/fail check. `make benchmark` SHALL run them through `TaskWorkflow` and record, per task, pass/fail, harness and inner turns, tokens and wall time, plus the model, template version, harness version and prompt hash, in `docs/benchmarks/`. (Plan: Phase 1 task 5.)

#### Scenario: Baseline recorded
- **WHEN** `make benchmark` runs against the configured model for the first time
- **THEN** a results file in `docs/benchmarks/` records every task and is marked as the baseline

### Requirement: Regression limit
A benchmark run that passes 2 or more fewer tasks than the baseline SHALL block phase closure. (Plan: §8 benchmark rule; owner decision 2026-11-11: at most 1 task lost out of 10.)

#### Scenario: Regression detected
- **WHEN** a run passes 8 tasks against a baseline of 10
- **THEN** the run's report states that the regression limit is exceeded

### Requirement: When the benchmark runs
The benchmark SHALL be run after any change to a model, a template, a harness version or a system prompt, and at every phase closure from Phase 1 onward. (Plan: §8 benchmark rule.)

#### Scenario: Template changed
- **WHEN** a pull request changes `registry/templates/local-default.yaml`
- **THEN** the phase evidence links a benchmark run made after that change
