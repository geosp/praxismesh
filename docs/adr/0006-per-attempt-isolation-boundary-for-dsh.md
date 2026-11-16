---
id: ADR-0006
title: Isolate each DSH attempt with its own cgroup, UID and mount namespace, not its own container
status: accepted
date: 2026-11-15
issue: "#62"
related:
  - docs/adr/0005-adopt-dsh-as-primary-agent-harness.md
  - docs/plans/2026-11-15-dsh-production-harness/plan.md
supersedes: null
superseded_by: null
---

# ADR-0006: Isolate each DSH attempt with its own cgroup, UID and mount namespace, not its own container

## Context and problem statement

ADR-0005 condition 3 requires "one container per attempt with no host credentials".
The MVP runs on Docker Compose, where a worker can only start containers through
the Docker socket, which is root-equivalent on the host, or through a privileged
proxy. The migration plan instead pairs each worker with one credential-free DSH
container. This ADR amends condition 3; ADR-0005 otherwise stands.

## Considered options

- One container per attempt, started through a Docker socket or socket proxy.
- One paired DSH container per worker, with a per-attempt boundary inside it.
- LXC/Incus system containers per attempt.

## Decision outcome

Chosen option: "One paired DSH container per worker", because it needs no Docker
or container-start rights and works unchanged in Compose and later in a Kubernetes
pod. Condition 3 now reads: **one isolated boundary per attempt**. Each attempt
gets:
- its own cgroup;
- a separate UID for commands;
- a mount namespace that shows only that attempt's workspace;
- no credentials and no network.

DSH templates pin `concurrency_per_pod: 1`.

### Consequences

- Good, because no component gets root-equivalent rights on the host.
- Good, because the same design maps onto a Kubernetes pod.
- Bad, because attempts share one container's kernel-visible state; isolation
  rests on cgroup, UID and namespace setup, which the launcher must get right.
- Follow-up: the migration plan's cgroup probe (phase 01 task 0.1) must pass, or
  this decision returns to the owner.

### Confirmation

The migration plan's integration tests: a worker SIGKILL leaves no attempt process;
a backgrounded command is killed with its attempt; a command cannot read the session
files or another attempt's tree.

## Links

- [ADR-0005](0005-adopt-dsh-as-primary-agent-harness.md): adopt DSH; condition 3 amended here.
- [Migration plan](../plans/2026-11-15-dsh-production-harness/plan.md), D3.
