#!/bin/bash
# The backup and restore drill (Phase 3A persistence plan phase 03 task 2.3; R16,
# R17, R23, D8; notes.md#d8). Run through `make drill`, on a stack started with
# `make up` and migrated. It DELETES THE STACK'S DATA (`make reset`), so it is
# opt-in and never part of `make smoke`.
#
#  1. Run a task on the fake model through the worker containers.
#  2. Back up; the workers run again afterwards.
#  3. Restore into the same stack: refused, nothing changes (R23).
#  4. `make reset`, `make up`; a restore killed (SIGKILL) while it loads; the
#     next restore refuses; `make reset`, `make up` again.
#  5. Restore: `task status`, `task output` and the comms role work (R16).
#  6. Remove one restored object, the task's input: reconcile lists it as
#     dangling, held by the task's row and its upload, and exits 1 (R17).
#
# DRILL_BUILD=--no-build reuses the worker image instead of building it.
set -euo pipefail

: "${PROJECT_NAME:?run this through 'make drill'}"
: "${ENV_FILE:?run this through 'make drill'}"
MAKE=${MAKE:-make}
BUILD=${DRILL_BUILD:---build}
WORKERS="orchestrator worker-a worker-b"
OUTPUT=order-summary.md

compose() { docker compose -p "$PROJECT_NAME" --env-file "$ENV_FILE" -f infra/docker-compose.yml "$@"; }
uv_run() { uv run --env-file "$ENV_FILE" "$@"; }
cli() { uv_run python -m orchestrator.cli "$@"; }
mk() { "$MAKE" --no-print-directory ENV_FILE="$ENV_FILE" "$@"; }
step() { echo; echo "drill: $*"; }
fail() { echo "drill: FAILED: $*" >&2; exit 1; }
json() { python3 -c "import json, sys; d = json.loads(sys.stdin.read()); print($1)"; }
running() { compose ps --services --status running; }

scratch=$(mktemp -d)
backup="backups/drill-$(date -u +%Y%m%dT%H%M%SZ)"
trap 'rm -rf "$scratch"' EXIT

step "1. a task on the fake model"
VLLM_BASE_URL=http://fake-model:8765 compose --profile workers --profile fake-model \
    up -d "$BUILD" --wait --wait-timeout 300 fake-model $WORKERS
# Unique bytes, so no other task shares the blob step 6 removes.
printf 'sku,qty\nSKU-1,3\n# drill %s\n' "$(date -u +%s%N)" >"$scratch/orders.csv"
cli task submit --profile openai --wait --input "$scratch/orders.csv" --output "$OUTPUT" \
    --instructions "Order 3 units of SKU-1 and write order-summary.md." >"$scratch/submit.out"
task=$(head -1 "$scratch/submit.out" | json "d['task_id']")
status=$(sed 1d "$scratch/submit.out" | json "d['status']")
[ "$status" = succeeded ] || fail "task $task ended $status"
cli task output "$task" "$OUTPUT" >"$scratch/before.md"
echo "task $task succeeded"

step "2. backup into $backup"
cli backup --to "$backup"
for w in $WORKERS; do
    running | grep -qx "$w" || fail "worker $w is not running after the backup"
done
echo "the workers run again"

step "3. restore into a stack that holds data is refused"
if mk restore BACKUP="$backup" >"$scratch/refused.out" 2>&1; then
    fail "restore into a stack with data succeeded"
fi
grep -q "refusing to restore" "$scratch/refused.out" || { cat "$scratch/refused.out"; fail "no refusal"; }
cli task output "$task" "$OUTPUT" | cmp -s - "$scratch/before.md" || fail "the refusal changed the task"
echo "refused; the task's output is unchanged"

step "4. reset, then a restore killed while it loads"
mk reset
mk up
# Job control gives the restore its own process group, which the kill takes
# whole: the script and the docker compose client loading the dump.
set -m
PROJECT_NAME="$PROJECT_NAME" ENV_FILE="$ENV_FILE" bash infra/restore.sh "$backup" \
    >"$scratch/killed.out" 2>&1 &
pid=$!
set +m
for _ in $(seq 1200); do
    grep -q "restore: loading" "$scratch/killed.out" && break
    kill -0 "$pid" 2>/dev/null || break
    sleep 0.1
done
grep -q "restore: loading" "$scratch/killed.out" || { cat "$scratch/killed.out"; fail "restore never loaded"; }
kill -KILL -- "-$pid" 2>/dev/null || true
wait "$pid" 2>/dev/null || true
grep -q "restore: done" "$scratch/killed.out" && fail "restore finished before the kill"
echo "killed during: $(grep 'restore: loading' "$scratch/killed.out" | tail -1)"
if mk restore BACKUP="$backup" >"$scratch/after-kill.out" 2>&1; then
    fail "a restore after a killed one did not refuse"
fi
grep -q "an earlier restore did not finish" "$scratch/after-kill.out" || fail "no unfinished-restore refusal"
echo "the next restore refuses; reset and up again"
mk reset
mk up

step "5. restore"
mk restore BACKUP="$backup" | tee "$scratch/restore.out"
grep -q "restore: done" "$scratch/restore.out" || fail "restore did not finish"
[ "$(cli task status "$task" | json "d['task']['status']")" = succeeded ] || fail "task status"
cli task output "$task" "$OUTPUT" | cmp -s - "$scratch/before.md" || fail "task output differs"
uv_run python - "$task" <<'EOF' || fail "comms_mcp's role cannot connect"
import asyncio, os, sys
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
async def main() -> None:
    engine = create_async_engine(os.environ["PRAXIS_COMMS_DB_URL"])
    async with engine.connect() as conn:
        user = await conn.scalar(text("SELECT current_user"))
        seen = await conn.scalar(text("SELECT count(*) FROM tasks WHERE task_id = :t"), {"t": sys.argv[1]})
    await engine.dispose()
    assert (user, seen) == ("praxis_comms", 1), (user, seen)
    print(f"comms role {user} reads the restored task")
asyncio.run(main())
EOF

step "6. a removed object is reported dangling"
cli reconcile >"$scratch/clean.json" || true
key=$(cli task status "$task" | json "d['task']['input_refs']['orders.csv']['key']")
uv_run python - "$key" <<'EOF'
import sys
from common.blob_store.s3 import S3BlobStore
s3 = S3BlobStore.from_env()
s3.client.delete_object(Bucket=s3.bucket, Key=sys.argv[1])
print(f"removed {sys.argv[1]} from the bucket")
EOF
if cli reconcile >"$scratch/dangling.json"; then fail "reconcile exited 0 with a missing blob"; fi
python3 - "$scratch/clean.json" "$scratch/dangling.json" "$key" "$task" <<'EOF'
import json, sys
before, after = (json.load(open(p))["dangling"] for p in sys.argv[1:3])
key, task = sys.argv[3], sys.argv[4]
new = [d for d in after if d not in before]
# The removed input, as held by its task's row and by the task's upload.
want = {f"tasks/{task}/input_refs", f"upload/{task}"}
assert {d["holder"] for d in new} == want and all(d["blob_key"] == key for d in new), new
print("reconcile lists the removed input as dangling: " + ", ".join(sorted(want)))
EOF

rm -rf "$backup"
echo
echo "drill: passed"
