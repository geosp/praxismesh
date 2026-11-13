# Real-model PR #53 continuation evidence

Code: `9472d20d3b5e5d7cee1542ffedf9c25335defadd`.
Docs: `f2789d505755397bfdd40a88106a04a0b192f3cf`.
Date: 2026-11-13. Earlier blocked evidence remains preserved separately.

Only the credential-free model URL/name were supplied by the user. The model
host is redacted as `<configured-model>` in preserved logs. No configuration
files, keys, raw message/session histories or raw trace payloads are included.
Checkpoint JSON contains only counts, positions, archive filenames, tool names
and skill-read paths; task status JSON contains task/result/attempt references.
Terminal trailing whitespace is normalized; substantive output is preserved.

The `.py.txt` files preserve optional read-only evidence inspectors invoked by
the command ledger, not production changes or extra runtime prerequisites.
To reproduce their exact invocations, copy them to the named `.verify/*.py`
paths in a disposable checkout. They use the locked project dependencies.

Benchmark timings overlapped sample/recovery traffic on the same model server;
its workers used separate queues. These are observed task timings, not isolated
performance measurements. The committed benchmark baseline was unchanged.

The second verifier's scratch `asbuilt-*.jsonl` metadata is preserved as JSON
arrays in `asbuilt-*.json`; each original line is one array element. The
`asbuilt_*.py.txt` files preserve its read-only probes. No raw trace or session
file was saved. An attempted raw-trace-save probe was rejected before execution;
the verifier completed with whitelisted metadata instead.
