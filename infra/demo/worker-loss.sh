#!/bin/sh
# Phase 1 demo step 2: lose the worker container running a task (docs/demos/phase-1.md).
#
#     make demo-worker-loss          # needs `make workers-up` and a model endpoint
#
# Submits a task, waits until it has a checkpoint after its first model call
# (visible in `make task-status`), finds the container holding the attempt from
# the attempt's worker identity (<container hostname>@<pid>/<template>), and
# stops it abruptly with `docker kill` (a crashed container gets no grace period;
# decision log 2026-11-12). Then waits for the task and shows the attempts and
# orders. Afterwards: `docker start <container>` or `make workers-up`.
set -eu

ENV_FILE=${ENV_FILE:-infra/.env}
UV="uv run --env-file $ENV_FILE"
CHECKPOINTS=${CHECKPOINTS:-2}

status() { $UV python -m orchestrator.cli task status "$1"; }
field() { python3 -c "import json,sys; d=json.load(sys.stdin); print($1)"; }

id=$($UV python -m orchestrator.cli task submit --output order-summary.md --instructions \
    "Use the order-desk skill. Order 2 units of SKU-4, 1 unit of SKU-5, 3 units of SKU-2 and 1 unit of SKU-1: look up each price and stock, record each order once, and write order-summary.md." \
    | field "d['task_id']")
echo "task: $id"

i=0
until [ "$(status "$id" | field "d['checkpoints']")" -ge "$CHECKPOINTS" ]; do
    i=$((i + 1))
    [ "$i" -lt 600 ] || { echo "error: no checkpoint after 120 s" >&2; exit 1; }
    sleep 0.2
done
holder=$(status "$id" | field "d['attempts'][-1]['worker_identity']")
container=$(docker ps --filter "id=${holder%%@*}" --format '{{.Names}}')
[ -n "$container" ] || { echo "error: no running container for $holder" >&2; exit 1; }
echo "latest checkpoint: $(status "$id" | field "d['latest_checkpoint']['checkpoint_id']")"
docker kill "$container" >/dev/null
echo "killed $container (abrupt stop)"

i=0
until [ "$(status "$id" | field "d['task']['status']")" != running ]; do
    i=$((i + 1))
    [ "$i" -lt 300 ] || { echo "error: task still running after 300 s" >&2; exit 1; }
    sleep 1
done
status "$id" | python3 -c "
import json, sys
d = json.load(sys.stdin)
print('task status:', d['task']['status'], '| workflow:', d['workflow'])
for a in d['attempts']:
    print(f\"  turn {a['turn']} attempt {a['attempt']}: {a['outcome']} on {a['worker_identity'].split('@')[0]}\")
print('orders:', d['orders'])
"
echo "restart it with: docker start $container"
