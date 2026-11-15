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
