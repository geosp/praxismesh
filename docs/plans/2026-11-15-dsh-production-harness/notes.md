# Notes · Run production agents on DSH

## D2

Spike modules and what each becomes:

| Spike module | Production role |
| --- | --- |
| `task_policy.py` | failure classification, heartbeat progress, ownership order, manifest validation |
| `usage_ledger.py`, `task_boundary.py` | gateway admission and usage ledger |
| `recovery_boundary.py` (`ToolExecutor`), `bench_tools.py` | executor with production tool and skill semantics |
| `recovery_store.py` | barrier capture and acknowledgement, mapped onto checkpoint blobs and rows |
| `task_activity.py` | `DshRunner` and its container lifecycle |

The spike's frozen evidence (`docs/spikes/dsh-phase02-r2-evidence.json`) is the
reference for expected behaviour of each ported case.

## D3

| Target | Mechanism | Grant | Trade-off |
| --- | --- | --- | --- |
| Docker Compose | sibling container through a socket proxy | create/remove of the pinned image, fixed mounts | proxy is one more component; plain socket is root-equivalent |
| Kubernetes | per-attempt Pod created by the worker | service account limited to pods in one namespace | adds Pod start-up time per attempt |
| Either (chosen) | paired DSH container with a launcher; worker holds credentials, gateway and executor; shared attempt volume | none beyond normal deployment | process-group/cgroup isolation per attempt instead of a fresh container |
| Either | LXC/Incus system containers | Incus API access, scoped by project | second host runtime; still needs start rights; no Kubernetes path |
