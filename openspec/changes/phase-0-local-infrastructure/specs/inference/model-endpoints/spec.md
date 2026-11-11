# Spec Delta

## Purpose

Access to the local model servers in both API styles the platform uses: Anthropic Messages for Claude harnesses and OpenAI chat for plain model calls (plan §2 local models; Pre-0 spike).

## ADDED Requirements

### Requirement: External model endpoint by configuration
The stack SHALL reach vLLM through `VLLM_BASE_URL`, `VLLM_MODEL` and `VLLM_API_KEY` in `.env` (by default the external DGX Spark pair, one base URL for both API styles). Model name, base URL and key SHALL be configuration, never hard-coded. The model's launch flags SHALL be recorded (`docs/spikes/harness-vllm.md`). (Plan: Phase 0 task 2; §2; decision log 2026-11-10 hardware roles.)

#### Scenario: Endpoint from configuration
- **WHEN** `VLLM_BASE_URL` is set in `.env`
- **THEN** the model smoke tests call that endpoint and no other

### Requirement: Both API styles answer
The configured endpoint SHALL answer a real prompt on `/v1/messages` (Anthropic Messages) and on `/v1/chat/completions` (OpenAI chat). The served model name (`VLLM_MODEL`) SHALL NOT contain the `/` character. Phase 0 closes only with a recorded run in which these tests passed against the Sparks. (Plan: Phase 0 tasks 2 and 4.)

#### Scenario: Both endpoints
- **WHEN** the model smoke tests send a short prompt to each endpoint
- **THEN** each returns a non-empty reply

#### Scenario: Endpoint not configured
- **WHEN** `VLLM_BASE_URL` is unset
- **THEN** the model smoke tests are skipped with that reason

#### Scenario: Endpoint unreachable
- **WHEN** `VLLM_BASE_URL` is set but cannot be reached
- **THEN** the model smoke tests fail, naming the endpoint as unreachable
