# Agent benchmark: local-default@1, 2026-11-12

**Passed 10 of 10.** Recorded as the baseline (docs/benchmarks/baseline.json).

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
| t01-order-total | pass | ok | 2 | 9 | 2 | 19 | 23218 | 1798 | 39.3 |
| t02-restock | pass | ok | 1 | 8 | 1 | 16 | 17045 | 1155 | 27.2 |
| t03-fix-discount | pass | ok | 1 | 5 | 1 | 7 | 10304 | 709 | 16.3 |
| t04-config-port | pass | ok | 1 | 6 | 1 | 8 | 11042 | 718 | 16.9 |
| t05-sort-expensive | pass | ok | 1 | 7 | 1 | 11 | 14615 | 1073 | 24.2 |
| t06-git-commit | pass | ok | 1 | 8 | 1 | 8 | 17432 | 792 | 20.0 |
| t07-log-status | pass | ok | 1 | 5 | 1 | 6 | 8839 | 639 | 15.2 |
| t08-fill-prices | pass | ok | 1 | 7 | 1 | 12 | 16159 | 1089 | 25.4 |
| t09-report-table | pass | ok | 1 | 6 | 1 | 12 | 13589 | 1244 | 27.3 |
| t10-fix-script | pass | ok | 1 | 5 | 1 | 6 | 8531 | 524 | 13.4 |
