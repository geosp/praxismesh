# Spec Delta

## Purpose

Access to the local model servers in both API styles the platform uses: Anthropic Messages for Claude harnesses and OpenAI chat for plain model calls (plan §2 local models; Pre-0 spike).

## ADDED Requirements

### Requirement: External model endpoint by configuration
The stack SHALL reach vLLM through an endpoint configured in `.env` (by default the external DGX Spark server). Running vLLM inside Compose SHALL be an optional profile, off by default. Model name, base URL and API style SHALL be configuration, never hard-coded. (Plan: Phase 0 task 2; §2; decision log 2026-11-10 hardware roles.)

#### Scenario: Endpoint from configuration
- **WHEN** `VLLM_BASE_URL` is set in `.env`
- **THEN** the model smoke tests call that endpoint and no other

### Requirement: Both API styles answer
The configured endpoint SHALL answer a real prompt on `/v1/messages` (Anthropic Messages) and on `/v1/chat/completions` (OpenAI chat). The served model name SHALL contain no `/`. (Plan: Phase 0 tasks 2 and 4.)

#### Scenario: Both endpoints
- **WHEN** the model smoke tests send a short prompt to each endpoint
- **THEN** each returns a non-empty reply

#### Scenario: Endpoint unreachable
- **WHEN** the configured endpoint cannot be reached
- **THEN** the model smoke tests are reported as skipped or failed with the endpoint named as unreachable, never as passed
