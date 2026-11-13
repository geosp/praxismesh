# Agent benchmark: local-default@1, 2026-11-13

**Passed 10 of 10.** Within the regression limit (baseline 10).

| Item | Value |
|---|---|
| template | `local-default@1` |
| template_hash | `sha256:6122e8de71a551797b991d7ce87c701c366623076a63135b2f40e3f4b6e7f7ee` |
| model | `spark` |
| harness | `openai-agents 0.24.0` |
| prompt_hash | `sha256:9de242aeec2e5ed13fe20e67ef1975e2bb05c4b9ab32b7e3fbfe202b479dab15` |
| Model endpoint | the DGX Spark endpoint (vLLM) |

| Task | Result | Check | Turns | Inner turns | Attempts | Tool calls | Tokens in | Tokens out | Seconds |
|---|---|---|---|---|---|---|---|---|---|
| t01-order-total | pass | ok | 1 | 8 | 1 | 21 | 20103 | 1534 | 38.8 |
| t02-restock | pass | ok | 1 | 7 | 1 | 13 | 14389 | 997 | 25.0 |
| t03-fix-discount | pass | ok | 1 | 4 | 1 | 6 | 7507 | 699 | 20.7 |
| t04-config-port | pass | ok | 1 | 5 | 1 | 7 | 9214 | 635 | 15.2 |
| t05-sort-expensive | pass | ok | 1 | 5 | 1 | 12 | 10069 | 913 | 19.8 |
| t06-git-commit | pass | ok | 1 | 6 | 1 | 7 | 12421 | 615 | 15.3 |
| t07-log-status | pass | ok | 1 | 5 | 1 | 6 | 8606 | 502 | 12.5 |
| t08-fill-prices | pass | ok | 1 | 7 | 1 | 12 | 15004 | 770 | 18.9 |
| t09-report-table | pass | ok | 1 | 6 | 1 | 13 | 14460 | 1264 | 27.8 |
| t10-fix-script | pass | ok | 1 | 5 | 1 | 6 | 8918 | 665 | 16.2 |
