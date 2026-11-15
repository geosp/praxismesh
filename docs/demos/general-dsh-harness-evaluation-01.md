---
phase: general-dsh-harness-evaluation-01
code_sha: 65d03f0fdb56d8939e99d67156ddea398185a21f
docs_sha: 65d03f0fdb56d8939e99d67156ddea398185a21f
date: 2026-11-14
verdict: pass
---

# DSH evaluation Phase 01: independent demo

This is the isolated spike Phase 01, not closed runtime Phase 1. Suggested delivery path: `docs/demos/general-dsh-harness-evaluation-01.md`. Evidence executed 2026-11-15 UTC / 2026-11-14 America/New_York.

Frozen source: [PR63](https://github.com/geosp/praxismesh/pull/63), [tested commit](https://github.com/geosp/praxismesh/commit/65d03f0fdb56d8939e99d67156ddea398185a21f). No phase closure, adoption or merge action is performed.

## Environment and setup

Linux x86_64; glibc 2.43; uv 0.13.5; Docker 29.9.3; locked root/spike CPython 3.11.17; SDK/runtime 0.2.2rc2. System Python 3.14.10 was not the selected environment. `UV_CACHE_DIR=/tmp/praxismesh-skill-audit-cache` was used. Only the noncredential model URL scratch input was operator supplied; no deployment environment or credential file was copied.

Run from disposable checkout root:

```bash
uv sync --locked
uv sync --project spikes/dsh-harness --locked --python 3.11
spikes/dsh-harness/.venv/bin/python spikes/dsh-harness/preflight.py
docker pull python@sha256:a83ba18aef0f865b1a4a611c2cf460fe446f2795673bbb9fe43be570439e3b39
docker build --network none --build-arg SPIKE_UID="$(id -u)" --build-arg SPIKE_GID="$(id -g)" --iidfile .verify/acceptance-image-id spikes/dsh-harness
```

Expected: locked Python 3.11 setup, complete artifact hashes and local image build; observed all exit 0 with hashes/image below. Image-ID output uses a checkout-owned path instead of the shared `/tmp/praxis-dsh-image-id`; no candidate configuration changed. Docker/socket access required authorized execution outside the restricted sandbox; initial denials are retained in the raw acceptance report. Every actual probe below ran once after prerequisites were available.

Raw original acceptance report: `.verify/acceptance-report.md`; complete command records and immutable manifests: `.verify/raw/acceptance-*`. Original failed environmental/ancillary attempts remain there. The final verification report records their classification and evidence completeness.

# Independent Phase 01 demonstration evidence

Verdict: **PASS, seven documented cases on frozen code 65d03f0fdb56d8939e99d67156ddea398185a21f.** All cases ran once after prerequisites were established; no functional demo was retried. Automated diagnostics and environmental failures are detailed in acceptance-report.md.

Environment/setup commands and image build output: acceptance-report.md. Image ID: `sha256:2c3b7f62f7757863ae2d75fdf05d751b32ba24cb06a5aea5251b2d79067f7f2d`. Separate environments use Python 3.11.17 and SDK/runtime 0.2.2rc2. SHA values in artifacts are identities rather than independent binary build-provenance proof.

Execution was only through the documented run_probe controller with local Docker and bounded gateway. The live endpoint came only from .verify/local-model-url via VLLM_BASE_URL at execution; no endpoint or credential value was printed or copied into evidence. Disposable checkout had no infra/.env. All other providers were scripted; they establish control behavior rather than live-model compatibility.

Expected for every case: process exit 0, initialized true, host environment absent, direct IP blocked, policy/catalog unchanged where model requests occur, container_absent and cleanup_ok true. Catalog is exactly skill plus lookup_price and lookup_stock.

| Case | Owned container | Requests | Admitted fixture tool entries | Result |
| --- | --- | --- | --- | --- |
| startup | praxis-dsh-add23ab3cc58 | 0 | 0 | PASS |
| catalog | praxis-dsh-5f675bc7026c | 1 | 0 | PASS |
| capability | praxis-dsh-6ad062897be1 | 4 | 2 | PASS |
| poison | praxis-dsh-4efc7a9260af | 5 | 2 | PASS |
| denied-tool | praxis-dsh-edff2d92c9c4 | 2 | 0 | PASS |
| native-text | praxis-dsh-12e851ea2c6f | 2 | 0 | PASS |
| local | praxis-dsh-c0910549ecc5 | 2 | 2 | PASS |

Local observed provider usage: prompt tokens 738 + 1542 = **2280 input**; completion tokens 517 + 72 = **589 output**; sum **2869**. Provider total_tokens not added again; reasoning-token breakdown not added again. This is a live boundary observation, not the Phase 02 comprehensive budget/retry reconciliation.

## startup — PASS

Command: `spikes/dsh-harness/.venv/bin/python spikes/dsh-harness/run_probe.py startup --image "$(cat .verify/acceptance-image-id)"`

Expected: No model request; explicit SDK/runtime startup succeeds.

Observed: command exit 0; persisted manifest digest `c273bc1aab7d35b057f578c2ef88169a0e60dab3953d5099856fd358b0f12c04` independently matched exact copied manifest bytes. Root session `probe`; Activity-attempt label 1; no Temporal Activity launched. Container `praxis-dsh-add23ab3cc58`.

```json
{
  "case": "startup",
  "exit": 0,
  "manifest_sha256": "c273bc1aab7d35b057f578c2ef88169a0e60dab3953d5099856fd358b0f12c04",
  "seconds": 1.476,
  "stdout": "{\"case\": \"startup\", \"initialized\": true, \"profile\": \"sdk-minimal\", \"host_environment_absent\": true, \"direct_ip_blocked\": true}\n",
  "stderr": "",
  "container_absent": true,
  "cleanup_ok": true,
  "observations": 21,
  "cleanup_command_exit": 0,
  "grace_met": true,
  "observation_seconds": 10.014
}
```

Raw output: `raw/acceptance-startup.json`. Immutable input copy: `raw/acceptance-startup-manifest.json`. Original manifest: `spikes/dsh-harness/.runs/praxis-dsh-add23ab3cc58-manifest.json`.

## catalog — PASS

Command: `spikes/dsh-harness/.venv/bin/python spikes/dsh-harness/run_probe.py catalog --image "$(cat .verify/acceptance-image-id)"`

Expected: Exactly one observed request; exact three-tool catalog; no fixture bodies.

Observed: command exit 0; persisted manifest digest `dd979063ca66c3f292e0e68bcc8fb5bdac0aecd7004e5ed4cea9dc4f5a799f5c` independently matched exact copied manifest bytes. Root session `probe`; Activity-attempt label 1; no Temporal Activity launched. Container `praxis-dsh-5f675bc7026c`.

```json
{
  "case": "catalog",
  "exit": 0,
  "manifest_sha256": "dd979063ca66c3f292e0e68bcc8fb5bdac0aecd7004e5ed4cea9dc4f5a799f5c",
  "seconds": 2.425,
  "stdout": "{\"case\": \"catalog\", \"initialized\": true, \"profile\": \"sdk-minimal\", \"host_environment_absent\": true, \"direct_ip_blocked\": true, \"unapproved_gateway_path_blocked\": true, \"finish_reason\": \"completed\", \"policy_unchanged\": true, \"response_hash\": \"e7f099332273bb2648ff5ac9c4b14e5d7abe7f977ca9a1097001ce7bd93bb286\"}\n",
  "stderr": "",
  "gateway_stopped": true,
  "container_absent": true,
  "cleanup_ok": true,
  "observations": 20,
  "cleanup_command_exit": 0,
  "grace_met": true,
  "observation_seconds": 10.012,
  "model_requests": [
    {
      "sequence": 1,
      "path": "/v1/chat/completions",
      "request_hash": "03048d08111a7106019e397481c55ba152b37d4effe0a01ca47a4d8bd9559e92",
      "tools": [
        "mcp__sample-shop__lookup_price",
        "mcp__sample-shop__lookup_stock",
        "skill"
      ],
      "model": "spark",
      "poison_visible": false,
      "native_input_visible": false,
      "skill_body_seen": false,
      "denial_seen": false
    }
  ],
  "tool_executions": []
}
```

Raw output: `raw/acceptance-catalog.json`. Immutable input copy: `raw/acceptance-catalog-manifest.json`. Original manifest: `spikes/dsh-harness/.runs/praxis-dsh-5f675bc7026c-manifest.json`.

## capability — PASS

Command: `spikes/dsh-harness/.venv/bin/python spikes/dsh-harness/run_probe.py capability --image "$(cat .verify/acceptance-image-id)"`

Expected: Skill body visible; both allowed MCP fixture bodies entered; expected quote matches.

Observed: command exit 0; persisted manifest digest `cb63831721cf4edec47e22881ac6df6020327e24de4b514eb87be32a717cc91a` independently matched exact copied manifest bytes. Root session `probe`; Activity-attempt label 1; no Temporal Activity launched. Container `praxis-dsh-6ad062897be1`.

```json
{
  "case": "capability",
  "exit": 0,
  "manifest_sha256": "cb63831721cf4edec47e22881ac6df6020327e24de4b514eb87be32a717cc91a",
  "seconds": 2.449,
  "stdout": "{\"case\": \"capability\", \"initialized\": true, \"profile\": \"sdk-minimal\", \"host_environment_absent\": true, \"direct_ip_blocked\": true, \"unapproved_gateway_path_blocked\": true, \"finish_reason\": \"completed\", \"policy_unchanged\": true, \"response_hash\": \"e7f099332273bb2648ff5ac9c4b14e5d7abe7f977ca9a1097001ce7bd93bb286\", \"quote_matches\": true}\n",
  "stderr": "",
  "gateway_stopped": true,
  "container_absent": true,
  "cleanup_ok": true,
  "observations": 20,
  "cleanup_command_exit": 0,
  "grace_met": true,
  "observation_seconds": 10.013,
  "model_requests": [
    {
      "sequence": 1,
      "path": "/v1/chat/completions",
      "request_hash": "03048d08111a7106019e397481c55ba152b37d4effe0a01ca47a4d8bd9559e92",
      "tools": [
        "mcp__sample-shop__lookup_price",
        "mcp__sample-shop__lookup_stock",
        "skill"
      ],
      "model": "spark",
      "poison_visible": false,
      "native_input_visible": false,
      "skill_body_seen": false,
      "denial_seen": false
    },
    {
      "sequence": 2,
      "path": "/v1/chat/completions",
      "request_hash": "2399577bb8aaedcd49b2403a35140a115f4831a6c298201545001b8e25af786e",
      "tools": [
        "mcp__sample-shop__lookup_price",
        "mcp__sample-shop__lookup_stock",
        "skill"
      ],
      "model": "spark",
      "poison_visible": false,
      "native_input_visible": false,
      "skill_body_seen": true,
      "denial_seen": false
    },
    {
      "sequence": 3,
      "path": "/v1/chat/completions",
      "request_hash": "0120fa4598fffe7f6e6b7966264f070884bd5078468a388568170f87e50d232c",
      "tools": [
        "mcp__sample-shop__lookup_price",
        "mcp__sample-shop__lookup_stock",
        "skill"
      ],
      "model": "spark",
      "poison_visible": false,
      "native_input_visible": false,
      "skill_body_seen": true,
      "denial_seen": false
    },
    {
      "sequence": 4,
      "path": "/v1/chat/completions",
      "request_hash": "317e3900175a10d464f1ee78d448dbc4e71fcc7304307a568b5ff6a42f008a34",
      "tools": [
        "mcp__sample-shop__lookup_price",
        "mcp__sample-shop__lookup_stock",
        "skill"
      ],
      "model": "spark",
      "poison_visible": false,
      "native_input_visible": false,
      "skill_body_seen": true,
      "denial_seen": false
    }
  ],
  "tool_executions": [
    {
      "tool": "lookup_price",
      "admitted": true
    },
    {
      "tool": "lookup_stock",
      "admitted": true
    }
  ]
}
```

Raw output: `raw/acceptance-capability.json`. Immutable input copy: `raw/acceptance-capability-manifest.json`. Original manifest: `spikes/dsh-harness/.runs/praxis-dsh-6ad062897be1-manifest.json`.

## poison — PASS

Command: `spikes/dsh-harness/.venv/bin/python spikes/dsh-harness/run_probe.py poison --image "$(cat .verify/acceptance-image-id)"`

Expected: Poison discovery absent; allowed quote still works; denied introduced plugin operation observed; grants unchanged.

Observed: command exit 0; persisted manifest digest `d23fc867db960e7eb0bd50f72851a05ba9ff66717e5631a19d9050a09b99b3ec` independently matched exact copied manifest bytes. Root session `probe`; Activity-attempt label 1; no Temporal Activity launched. Container `praxis-dsh-4efc7a9260af`.

```json
{
  "case": "poison",
  "exit": 0,
  "manifest_sha256": "d23fc867db960e7eb0bd50f72851a05ba9ff66717e5631a19d9050a09b99b3ec",
  "seconds": 2.39,
  "stdout": "{\"case\": \"poison\", \"initialized\": true, \"profile\": \"sdk-minimal\", \"host_environment_absent\": true, \"direct_ip_blocked\": true, \"unapproved_gateway_path_blocked\": true, \"finish_reason\": \"completed\", \"policy_unchanged\": true, \"response_hash\": \"e7f099332273bb2648ff5ac9c4b14e5d7abe7f977ca9a1097001ce7bd93bb286\", \"quote_matches\": true}\n",
  "stderr": "",
  "gateway_stopped": true,
  "container_absent": true,
  "cleanup_ok": true,
  "observations": 20,
  "cleanup_command_exit": 0,
  "grace_met": true,
  "observation_seconds": 10.013,
  "model_requests": [
    {
      "sequence": 1,
      "path": "/v1/chat/completions",
      "request_hash": "03048d08111a7106019e397481c55ba152b37d4effe0a01ca47a4d8bd9559e92",
      "tools": [
        "mcp__sample-shop__lookup_price",
        "mcp__sample-shop__lookup_stock",
        "skill"
      ],
      "model": "spark",
      "poison_visible": false,
      "native_input_visible": false,
      "skill_body_seen": false,
      "denial_seen": false
    },
    {
      "sequence": 2,
      "path": "/v1/chat/completions",
      "request_hash": "2399577bb8aaedcd49b2403a35140a115f4831a6c298201545001b8e25af786e",
      "tools": [
        "mcp__sample-shop__lookup_price",
        "mcp__sample-shop__lookup_stock",
        "skill"
      ],
      "model": "spark",
      "poison_visible": false,
      "native_input_visible": false,
      "skill_body_seen": true,
      "denial_seen": false
    },
    {
      "sequence": 3,
      "path": "/v1/chat/completions",
      "request_hash": "0120fa4598fffe7f6e6b7966264f070884bd5078468a388568170f87e50d232c",
      "tools": [
        "mcp__sample-shop__lookup_price",
        "mcp__sample-shop__lookup_stock",
        "skill"
      ],
      "model": "spark",
      "poison_visible": false,
      "native_input_visible": false,
      "skill_body_seen": true,
      "denial_seen": false
    },
    {
      "sequence": 4,
      "path": "/v1/chat/completions",
      "request_hash": "317e3900175a10d464f1ee78d448dbc4e71fcc7304307a568b5ff6a42f008a34",
      "tools": [
        "mcp__sample-shop__lookup_price",
        "mcp__sample-shop__lookup_stock",
        "skill"
      ],
      "model": "spark",
      "poison_visible": false,
      "native_input_visible": false,
      "skill_body_seen": true,
      "denial_seen": false
    },
    {
      "sequence": 5,
      "path": "/v1/chat/completions",
      "request_hash": "b5c60e6606efbacb8f2ab703072157ced32151dcd8ae26978cf1eebd36dad6d6",
      "tools": [
        "mcp__sample-shop__lookup_price",
        "mcp__sample-shop__lookup_stock",
        "skill"
      ],
      "model": "spark",
      "poison_visible": false,
      "native_input_visible": false,
      "skill_body_seen": true,
      "denial_seen": true
    }
  ],
  "tool_executions": [
    {
      "tool": "lookup_price",
      "admitted": true
    },
    {
      "tool": "lookup_stock",
      "admitted": true
    }
  ]
}
```

Raw output: `raw/acceptance-poison.json`. Immutable input copy: `raw/acceptance-poison-manifest.json`. Original manifest: `spikes/dsh-harness/.runs/praxis-dsh-4efc7a9260af-manifest.json`.

## denied-tool — PASS

Command: `spikes/dsh-harness/.venv/bin/python spikes/dsh-harness/run_probe.py denied-tool --image "$(cat .verify/acceptance-image-id)"`

Expected: Exactly two requests; forbidden-call rejection observed; zero fixture bodies entered.

Observed: command exit 0; persisted manifest digest `6de41a7bef75a6b552d8799da0952a4862f530859d3357f76506ac6d6213b8fa` independently matched exact copied manifest bytes. Root session `probe`; Activity-attempt label 1; no Temporal Activity launched. Container `praxis-dsh-edff2d92c9c4`.

```json
{
  "case": "denied-tool",
  "exit": 0,
  "manifest_sha256": "6de41a7bef75a6b552d8799da0952a4862f530859d3357f76506ac6d6213b8fa",
  "seconds": 2.415,
  "stdout": "{\"case\": \"denied-tool\", \"initialized\": true, \"profile\": \"sdk-minimal\", \"host_environment_absent\": true, \"direct_ip_blocked\": true, \"unapproved_gateway_path_blocked\": true, \"finish_reason\": \"completed\", \"policy_unchanged\": true, \"response_hash\": \"e7f099332273bb2648ff5ac9c4b14e5d7abe7f977ca9a1097001ce7bd93bb286\"}\n",
  "stderr": "",
  "gateway_stopped": true,
  "container_absent": true,
  "cleanup_ok": true,
  "observations": 20,
  "cleanup_command_exit": 0,
  "grace_met": true,
  "observation_seconds": 10.012,
  "model_requests": [
    {
      "sequence": 1,
      "path": "/v1/chat/completions",
      "request_hash": "03048d08111a7106019e397481c55ba152b37d4effe0a01ca47a4d8bd9559e92",
      "tools": [
        "mcp__sample-shop__lookup_price",
        "mcp__sample-shop__lookup_stock",
        "skill"
      ],
      "model": "spark",
      "poison_visible": false,
      "native_input_visible": false,
      "skill_body_seen": false,
      "denial_seen": false
    },
    {
      "sequence": 2,
      "path": "/v1/chat/completions",
      "request_hash": "f20f32cd3302146deaf47e195f33fcede37e3ab164d73d3311f7c7c5008bb5d4",
      "tools": [
        "mcp__sample-shop__lookup_price",
        "mcp__sample-shop__lookup_stock",
        "skill"
      ],
      "model": "spark",
      "poison_visible": false,
      "native_input_visible": false,
      "skill_body_seen": false,
      "denial_seen": true
    }
  ],
  "tool_executions": []
}
```

Raw output: `raw/acceptance-denied-tool.json`. Immutable input copy: `raw/acceptance-denied-tool-manifest.json`. Original manifest: `spikes/dsh-harness/.runs/praxis-dsh-edff2d92c9c4-manifest.json`.

## native-text — PASS

Command: `spikes/dsh-harness/.venv/bin/python spikes/dsh-harness/run_probe.py native-text --image "$(cat .verify/acceptance-image-id)"`

Expected: Native-shaped task visible as model-input data; forbidden call rejected; exactly two requests and zero fixture bodies.

Observed: command exit 0; persisted manifest digest `dd48c8910c8c4c8d9b9a9abe9b021b8f6ed436338bffad7e0862da34fdd87cd7` independently matched exact copied manifest bytes. Root session `probe`; Activity-attempt label 1; no Temporal Activity launched. Container `praxis-dsh-12e851ea2c6f`.

```json
{
  "case": "native-text",
  "exit": 0,
  "manifest_sha256": "dd48c8910c8c4c8d9b9a9abe9b021b8f6ed436338bffad7e0862da34fdd87cd7",
  "seconds": 2.426,
  "stdout": "{\"case\": \"native-text\", \"initialized\": true, \"profile\": \"sdk-minimal\", \"host_environment_absent\": true, \"direct_ip_blocked\": true, \"unapproved_gateway_path_blocked\": true, \"finish_reason\": \"completed\", \"policy_unchanged\": true, \"response_hash\": \"e7f099332273bb2648ff5ac9c4b14e5d7abe7f977ca9a1097001ce7bd93bb286\"}\n",
  "stderr": "",
  "gateway_stopped": true,
  "container_absent": true,
  "cleanup_ok": true,
  "observations": 20,
  "cleanup_command_exit": 0,
  "grace_met": true,
  "observation_seconds": 10.013,
  "model_requests": [
    {
      "sequence": 1,
      "path": "/v1/chat/completions",
      "request_hash": "96ee639c6a2317f0661e3daa2e9b484c4cc55e08a8a2900667175f99db36ddfb",
      "tools": [
        "mcp__sample-shop__lookup_price",
        "mcp__sample-shop__lookup_stock",
        "skill"
      ],
      "model": "spark",
      "poison_visible": false,
      "native_input_visible": true,
      "skill_body_seen": false,
      "denial_seen": false
    },
    {
      "sequence": 2,
      "path": "/v1/chat/completions",
      "request_hash": "a777ef500ee6ca4a60adb59268fd01aa5d89ad4d18bc1c0db0aee1602a3e4c51",
      "tools": [
        "mcp__sample-shop__lookup_price",
        "mcp__sample-shop__lookup_stock",
        "skill"
      ],
      "model": "spark",
      "poison_visible": false,
      "native_input_visible": true,
      "skill_body_seen": false,
      "denial_seen": true
    }
  ],
  "tool_executions": []
}
```

Raw output: `raw/acceptance-native-text.json`. Immutable input copy: `raw/acceptance-native-text-manifest.json`. Original manifest: `spikes/dsh-harness/.runs/praxis-dsh-12e851ea2c6f-manifest.json`.

## local — PASS

Command: `VLLM_BASE_URL="$(cat .verify/local-model-url)" spikes/dsh-harness/.venv/bin/python spikes/dsh-harness/run_probe.py local --deadline 180 --image "$(cat .verify/acceptance-image-id)"`

Expected: Real local spark HTTP200 responses with authoritative usage, observed skill body and both allowed MCP tool entries; quote_matches true; no hosted fallback.

Observed: command exit 0; persisted manifest digest `d5db9135bccb0460135b3b1e7e35651102f63639a2c30af90b0b83c698edcd50` independently matched exact copied manifest bytes. Root session `probe`; Activity-attempt label 1; no Temporal Activity launched. Container `praxis-dsh-c0910549ecc5`.

```json
{
  "case": "local",
  "exit": 0,
  "manifest_sha256": "d5db9135bccb0460135b3b1e7e35651102f63639a2c30af90b0b83c698edcd50",
  "seconds": 14.617,
  "stdout": "{\"case\": \"local\", \"initialized\": true, \"profile\": \"sdk-minimal\", \"host_environment_absent\": true, \"direct_ip_blocked\": true, \"unapproved_gateway_path_blocked\": true, \"finish_reason\": \"completed\", \"policy_unchanged\": true, \"response_hash\": \"122075797970321a08deecb7bb8afe7dbe8437bf989266e4f7cc2d5923d55bd9\", \"quote_matches\": true}\n",
  "stderr": "",
  "gateway_stopped": true,
  "container_absent": true,
  "cleanup_ok": true,
  "observations": 21,
  "cleanup_command_exit": 0,
  "grace_met": true,
  "observation_seconds": 10.011,
  "model_requests": [
    {
      "sequence": 1,
      "path": "/v1/chat/completions",
      "request_hash": "03048d08111a7106019e397481c55ba152b37d4effe0a01ca47a4d8bd9559e92",
      "tools": [
        "mcp__sample-shop__lookup_price",
        "mcp__sample-shop__lookup_stock",
        "skill"
      ],
      "model": "spark",
      "poison_visible": false,
      "native_input_visible": false,
      "skill_body_seen": false,
      "denial_seen": false,
      "provider_status": 200,
      "provider_usage": {
        "prompt_tokens": 738,
        "total_tokens": 1255,
        "completion_tokens": 517,
        "completion_tokens_details": {
          "reasoning_tokens": 420
        }
      }
    },
    {
      "sequence": 2,
      "path": "/v1/chat/completions",
      "request_hash": "282c34719ff484adf2400854aab94a0b8116908a428edabd98d49845e2f5c9fe",
      "tools": [
        "mcp__sample-shop__lookup_price",
        "mcp__sample-shop__lookup_stock",
        "skill"
      ],
      "model": "spark",
      "poison_visible": false,
      "native_input_visible": false,
      "skill_body_seen": true,
      "denial_seen": false,
      "provider_status": 200,
      "provider_usage": {
        "prompt_tokens": 1542,
        "total_tokens": 1614,
        "completion_tokens": 72,
        "completion_tokens_details": {
          "reasoning_tokens": 53
        }
      }
    }
  ],
  "tool_executions": [
    {
      "tool": "lookup_price",
      "admitted": true
    },
    {
      "tool": "lookup_stock",
      "admitted": true
    }
  ]
}
```

Raw output: `raw/acceptance-local.json`. Immutable input copy: `raw/acceptance-local-manifest.json`. Original manifest: `spikes/dsh-harness/.runs/praxis-dsh-c0910549ecc5-manifest.json`.

## Failure/recovery and teardown

No candidate/demo failure occurred. Normal run_probe cleanup stopped and joined the host listener/handlers/provider sockets, removed its exact container, and observed absence through ten seconds. Each result records cleanup_command_exit 0, grace_met true, cleanup_ok true and container_absent true; all six gateway cases record gateway_stopped true. Scratch directory absence was independently checked after completion. Full Phase 02 R5 oracle remains explicitly pending.

Final independent teardown command: `python3 .verify/acceptance-cleanup`. Expected: successful exact-name Docker listings all empty, seven scratch directories absent, no owned gateway/probe processes. Observed exit 0:

```text
capability praxis-dsh-6ad062897be1 docker_exit=0 listing='' scratch_exists=False
catalog praxis-dsh-5f675bc7026c docker_exit=0 listing='' scratch_exists=False
denied-tool praxis-dsh-edff2d92c9c4 docker_exit=0 listing='' scratch_exists=False
local praxis-dsh-c0910549ecc5 docker_exit=0 listing='' scratch_exists=False
native-text praxis-dsh-12e851ea2c6f docker_exit=0 listing='' scratch_exists=False
poison praxis-dsh-4efc7a9260af docker_exit=0 listing='' scratch_exists=False
startup praxis-dsh-add23ab3cc58 docker_exit=0 listing='' scratch_exists=False
remaining_owned_gateway_or_probe_processes=[]
PASS all seven named containers absent; disposable directories absent; no owned gateway/probe processes
```

All original manifests and result JSON remain in ignored .runs; copied manifests and raw stdout are retained under .verify/raw. The installed .venv directories and locally built image remain as documented reusable prerequisites; no unrelated Docker state was pruned. No source/test/documentation changes, commits, branch changes, or remote writes occurred.
