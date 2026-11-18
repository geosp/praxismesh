#!/bin/sh
# Phase 2 events demo (docs/demos/phase-2-events.md; plan
# docs/plans/2026-11-18-phase-2-agent-events, task 4.1).
#
#     sh infra/demo/phase-2-events.sh [OUT_DIR]   # needs `make workers-up` and a model endpoint
#
# 1. Submits a DSH task (profile `default`) and follows its events with
#    `agentctl tail`.
# 2. Once the task has a checkpoint, kills the worker container holding the
#    attempt; the retried attempt's events open with a `reset` naming the
#    checkpoint it restored from.
# 3. Stops the first tail, resumes with `--after` its last offset, and checks the
#    two tails together show offsets 1..N once each.
# 4. Prunes below offset 10 and shows `tail --after 3` reporting the expiry first.
# Afterwards it restarts the killed container. Output files go to OUT_DIR.
set -eu

ENV_FILE=${ENV_FILE:-infra/.env}
export ENV_FILE
CTL=./agentctl
PROFILE=${PROFILE:-default}
OUT=${1:-$(mktemp -d)}
mkdir -p "$OUT"

field() { python3 -c "import json,sys; d=json.load(sys.stdin); print($1)"; }
status() { $CTL task status "$1" 2>/dev/null; }
offsets() { grep -E '^[0-9]+' "$1" | cut -f1; }

id=$($CTL task submit --profile "$PROFILE" --output order-summary.md --instructions \
    "Use the order-desk skill. Order 2 units of SKU-4, 1 unit of SKU-5, 3 units of SKU-2 and 1 unit of SKU-1: look up each price and stock, record each order once, and write order-summary.md." \
    2>/dev/null | field "d['task_id']")
echo "task: $id" | tee "$OUT/task.txt"

$CTL tail "$id" > "$OUT/tail-1.log" 2>"$OUT/tail-1.err" &
tail1=$!

i=0
until [ "$(status "$id" | field "d['checkpoints']")" -ge 2 ]; do
    i=$((i + 1))
    [ "$i" -lt 900 ] || { echo "error: no checkpoint after 180 s" >&2; exit 1; }
    sleep 0.2
done
holder=$(status "$id" | field "d['attempts'][-1]['worker_identity']")
container=$(docker ps --filter "id=${holder%%@*}" --format '{{.Names}}')
[ -n "$container" ] || { echo "error: no running container for $holder" >&2; exit 1; }
echo "latest checkpoint: $(status "$id" | field "d['latest_checkpoint']['checkpoint_id']")" | tee -a "$OUT/task.txt"
docker kill "$container" >/dev/null
echo "killed $container (abrupt stop)" | tee -a "$OUT/task.txt"

sleep 15
kill "$tail1" 2>/dev/null || true
wait "$tail1" 2>/dev/null || true
last=$(offsets "$OUT/tail-1.log" | tail -1)
echo "first tail stopped after offset $last" | tee -a "$OUT/task.txt"

# Follows until the Workflow closes, then reads once more to the end.
timeout 900 $CTL tail "$id" --after "$last" > "$OUT/tail-2.log" 2>"$OUT/tail-2.err"
echo "task status: $(status "$id" | field "d['task']['status']")" | tee -a "$OUT/task.txt"
docker start "$container" >/dev/null && echo "restarted $container" | tee -a "$OUT/task.txt"

all=$( (offsets "$OUT/tail-1.log"; offsets "$OUT/tail-2.log") | tr '\n' ' ')
n=$(offsets "$OUT/tail-2.log" | tail -1)
expected=$(seq 1 "$n" | tr '\n' ' ')
if [ "$all" = "$expected" ]; then
    echo "offsets across both tails: 1..$n, each once" | tee -a "$OUT/task.txt"
else
    echo "error: offsets across both tails are not 1..$n once each" | tee -a "$OUT/task.txt"
    exit 1
fi
cat "$OUT/tail-1.log" "$OUT/tail-2.log" | grep -P '\treset\t' | tee "$OUT/resets.txt"

$CTL events prune --task "$id" --below 10 2>/dev/null | tee "$OUT/prune.json"
$CTL tail "$id" --after 3 --no-follow > "$OUT/tail-after-prune.log" 2>/dev/null
head -2 "$OUT/tail-after-prune.log"
echo "output: $OUT"
