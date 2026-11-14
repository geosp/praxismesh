# PraxisMesh plan: external references (§11)

Part of the PraxisMesh project plan, revision 2.10. Start from the core plan: [PROJECT_PLAN.md](../../PROJECT_PLAN.md). Section numbers match the core plan's document map.

## 11. External references to verify at implementation

- OpenSpec installation: https://openspec.dev/docs/installation
- OpenSpec initialization and coding-tool integrations: https://github.com/Fission-AI/OpenSpec/blob/main/docs/cli.md

- Temporal Python SDK: https://docs.temporal.io/develop/python
- Temporal Worker deployment and performance: https://docs.temporal.io/best-practices/worker
- Temporal Worker Controller CRDs and naming: https://github.com/temporalio/temporal-worker-controller/blob/main/docs/concepts.md
- Temporal Worker Controller KEDA scaling recommendations: https://github.com/temporalio/temporal-worker-controller/blob/main/docs/scaling-recommendations.md
- Temporal Workflow Streams SDK (experimental interface; verify before use): https://github.com/temporalio/sdk-python/blob/main/temporalio/contrib/workflow_streams/README.md
- SeaweedFS: https://github.com/seaweedfs/seaweedfs
- Temporal Workflow Streams, Python guide: https://docs.temporal.io/develop/python/workflows/workflow-streams
- Temporal Workflow Streams, Python API reference: https://python.temporal.io/temporalio.contrib.workflow_streams.html
- Temporal Worker Controller CRD management and rename migration: https://github.com/temporalio/temporal-worker-controller/blob/main/docs/crd-management.md
- OpenSpec customization and custom schemas: https://raw.githubusercontent.com/Fission-AI/OpenSpec/main/docs/customization.md
- GitHub MCP server: https://github.com/github/github-mcp-server
- Claude Agent SDK overview, including branding and license notes: https://code.claude.com/docs/en/agent-sdk/overview
- Claude Code legal and compliance: https://code.claude.com/docs/en/legal-and-compliance
- Claude Code with LLM gateways (`ANTHROPIC_BASE_URL`): https://code.claude.com/docs/en/llm-gateway

**Listed in §2 but with no recorded reference yet (locate the official source and add it here when verifying):** `claude-agent-sdk` and its session persistence/resume behavior; `temporalio-mcp`; vLLM Anthropic Messages endpoint and tool-call parser settings; KEDA Temporal scaler; `kopf`.
