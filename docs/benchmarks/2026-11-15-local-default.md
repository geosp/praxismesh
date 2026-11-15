# Agent benchmark: local-default@1, 2026-11-15

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
| t01-order-total | pass | ok | 1 | 7 | 1 | 16 | 17697 | 1560 | 34.1 |
| t02-restock | pass | ok | 1 | 7 | 1 | 14 | 17833 | 1585 | 34.5 |
| t03-fix-discount | pass | ok | 1 | 6 | 1 | 7 | 10901 | 614 | 15.3 |
| t04-config-port | pass | ok | 1 | 6 | 1 | 8 | 11161 | 753 | 18.0 |
| t05-sort-expensive | pass | ok | 1 | 5 | 1 | 10 | 9997 | 847 | 18.9 |
| t06-git-commit | pass | ok | 1 | 6 | 1 | 7 | 12850 | 891 | 20.5 |
| t07-log-status | pass | ok | 1 | 4 | 1 | 5 | 6767 | 626 | 14.7 |
| t08-fill-prices | pass | ok | 1 | 8 | 1 | 12 | 16256 | 1056 | 24.9 |
| t09-report-table | pass | ok | 1 | 5 | 1 | 11 | 10947 | 1307 | 28.0 |
| t10-fix-script | pass | ok | 1 | 5 | 1 | 7 | 8760 | 554 | 13.7 |
