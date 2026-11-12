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

| Task | Result | Check | Turns | Attempts | Tool calls | Tokens in | Tokens out | Seconds |
|---|---|---|---|---|---|---|---|---|
| t01-order-total | pass | ok | 1 | 1 | 18 | 19717 | 2242 | 48.4 |
| t02-restock | pass | ok | 1 | 1 | 14 | 14672 | 1335 | 30.6 |
| t03-fix-discount | pass | ok | 1 | 1 | 7 | 9437 | 749 | 18.0 |
| t04-config-port | pass | ok | 1 | 1 | 9 | 11291 | 659 | 16.9 |
| t05-sort-expensive | pass | ok | 1 | 1 | 11 | 10958 | 1275 | 27.7 |
| t06-git-commit | pass | ok | 1 | 1 | 7 | 14549 | 674 | 18.2 |
| t07-log-status | pass | ok | 1 | 1 | 5 | 6811 | 497 | 12.2 |
| t08-fill-prices | pass | ok | 1 | 1 | 12 | 15269 | 883 | 21.9 |
| t09-report-table | pass | ok | 1 | 1 | 12 | 12450 | 914 | 21.3 |
| t10-fix-script | pass | ok | 1 | 1 | 6 | 8690 | 558 | 14.3 |
