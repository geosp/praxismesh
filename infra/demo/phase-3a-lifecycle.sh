#!/bin/bash
# Phase 3A persistence and data lifecycle demo (docs/demos/phase-3a-lifecycle.md;
# plan docs/plans/2026-11-19-phase-3a-persistence-and-lifecycle, task 3.2).
#
#     ENV_FILE=infra/.env bash infra/demo/phase-3a-lifecycle.sh [OUT_DIR]
#
# It DELETES THE STACK'S DATA: it starts from `make reset`, `make up` and `make
# migrate`, because the fake model writes the same artifact for every task and
# a blob another task holds is kept (R3). It runs its tasks on the fake model
# through the worker containers, and resets the stack again before restoring
# the backup it took.
#
#  1. Request A: a task with an input and an artifact.
#  2. gc --dry-run, after setting A's end 91 days back (the only change made
#     outside agentctl), then gc: its tombstones, and A's artifact reads as
#     expired.
#  3. Request B: a task, deleted with request delete (dry run first): its
#     tombstones, its redacted status and no outputs.
#  4. Request C resubmits B's input: the removed blob is live again and gc
#     keeps it.
#  5. backup, make reset, make up, restore: its reconcile report, and C's
#     status and output.
#
# DEMO_BUILD=--no-build reuses the worker image instead of building it.
set -euo pipefail

ENV_FILE=${ENV_FILE:-infra/.env}
export ENV_FILE
OUT=${1:-$(mktemp -d)}
mkdir -p "$OUT"
BUILD=${DEMO_BUILD:---build}
PROJECT_NAME=$(sh infra/check-prereqs.sh --project-only "$ENV_FILE")
WORKERS="orchestrator worker-a worker-b"

CTL=./agentctl
compose() { docker compose -p "$PROJECT_NAME" --env-file "$ENV_FILE" -f infra/docker-compose.yml "$@"; }
probe() { PYTHONPATH=. uv run --env-file "$ENV_FILE" python infra/demo/lifecycle_probe.py "$@"; }
field() { python3 -c "import json, sys; d = json.loads(sys.stdin.read()); print($1)"; }
say() { echo; echo "== $*" | tee -a "$OUT/demo.log"; }
log() { tee -a "$OUT/demo.log"; }
fail() { echo "demo: FAILED: $*" >&2; exit 1; }

# submit NAME INPUT_FILE: runs a task in a new request; prints its task ID.
submit() {
    $CTL task submit --profile openai --wait --input "$2" --output order-summary.md \
        --instructions "Order 3 units of SKU-1 and write order-summary.md." \
        2>/dev/null >"$OUT/$1.submit"
    [ "$(sed 1d "$OUT/$1.submit" | field "d['status']")" = succeeded ] || fail "task $1 failed"
    head -1 "$OUT/$1.submit" | field "d['task_id']"
}

mk() { make --no-print-directory ENV_FILE="$ENV_FILE" "$@" >/dev/null 2>&1; }

say "0. a fresh stack, and workers on the fake model"
mk reset
mk up
mk migrate
VLLM_BASE_URL=http://fake-model:8765 compose --profile workers --profile fake-model \
    up -d "$BUILD" --wait --wait-timeout 300 fake-model $WORKERS >/dev/null 2>&1
stamp=$(date -u +%s%N)
printf 'sku,qty\nSKU-1,3\n# request A %s\n' "$stamp" >"$OUT/orders-a.csv"
printf 'sku,qty\nSKU-1,3\n# request B %s\n' "$stamp" >"$OUT/orders-b.csv"

say "1. request A: a task with an input and an artifact"
a=$(submit a "$OUT/orders-a.csv")
echo "task A: $a" | log
$CTL task output "$a" order-summary.md 2>/dev/null | head -3 | log

say "2. gc, after A's end is set 91 days back (artifacts live 90 days)"
probe age "$a" 91 | log
$CTL gc --dry-run 2>/dev/null | tee "$OUT/gc-dry.json" | log
$CTL gc 2>/dev/null | tee "$OUT/gc.json" | log
[ "$(field "d['blobs']" <"$OUT/gc.json")" -ge 1 ] || fail "gc removed no blob"
echo "tombstones:" | log
probe tombstones "$(field "d['operation']" <"$OUT/gc.json")" | log
if $CTL task output "$a" order-summary.md >/dev/null 2>"$OUT/a-output.err"; then
    fail "A's artifact still reads"
fi
grep -q expired "$OUT/a-output.err" || fail "A's artifact does not read as expired"
log <"$OUT/a-output.err"

say "3. request B: a task, then request delete"
b=$(submit b "$OUT/orders-b.csv")
req_b=$(head -1 "$OUT/b.submit" | field "d['request_id']")
echo "task B: $b, request $req_b" | log
$CTL request delete "$req_b" --dry-run 2>/dev/null | log
$CTL request delete "$req_b" 2>/dev/null | tee "$OUT/delete.json" | log
echo "tombstones:" | log
probe tombstones "$(field "d['operation']" <"$OUT/delete.json")" | log
$CTL task status "$b" 2>/dev/null |
    field "{k: d['task'][k] for k in ('status', 'ended_at')} | {'summary': d['task']['result']['summary'], 'artifacts': d['task']['result']['artifacts'], 'tokens_in': d['task']['result']['tokens_in']}" |
    log
grep -q '\[deleted ' <<<"$($CTL task status "$b" 2>/dev/null)" || fail "B's summary is not redacted"
if $CTL task output "$b" order-summary.md >/dev/null 2>"$OUT/b-output.err"; then
    fail "B's output still reads"
fi
log <"$OUT/b-output.err"

say "4. request C resubmits B's input: the removed blob is live again"
c=$(submit c "$OUT/orders-b.csv")
echo "task C: $c (succeeded, reading B's removed input)" | log
$CTL gc 2>/dev/null | tee "$OUT/gc-after-c.json" | log
$CTL task status "$c" 2>/dev/null | field "next(iter(d['task']['input_refs'].values()))['key']" >"$OUT/c-input.key"
probe tombstones "$(field "d['operation']" <"$OUT/gc-after-c.json")" >"$OUT/gc-after-c.tombstones"
if grep -qF "$(cat "$OUT/c-input.key")" "$OUT/gc-after-c.tombstones"; then
    fail "gc removed C's input"
fi
echo "gc kept C's input $(cat "$OUT/c-input.key")" | log

say "5. backup, make reset, make up, restore"
backup="backups/demo-$(date -u +%Y%m%dT%H%M%SZ)"
$CTL backup --to "$backup" 2>/dev/null | log
mk reset
mk up
make --no-print-directory ENV_FILE="$ENV_FILE" restore BACKUP="$backup" 2>&1 |
    grep -v '^ Container' | tee "$OUT/restore.out" | log
grep -q "restore: done" "$OUT/restore.out" || fail "restore did not finish"
$CTL task status "$c" 2>/dev/null | field "d['task']['status']" | sed 's/^/task C after the restore: /' | log
$CTL task output "$c" order-summary.md 2>/dev/null | head -3 | log
rm -rf "$backup"

say "demo passed; output in $OUT"
