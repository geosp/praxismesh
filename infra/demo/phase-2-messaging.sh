#!/bin/sh
# Phase 2 messaging demo (docs/demos/phase-2.md; plan
# docs/plans/2026-11-18-phase-2-events-and-comms, phase 03 task 2.1).
#
#     sh infra/demo/phase-2-messaging.sh [OUT_DIR]   # needs `make workers-up` and a model endpoint
#
# 1. Submits B, the price desk, which waits; then A in B's request, which asks B
#    a question and waits. An observer follows A with `agentctl tail`.
# 2. B is woken by the question and replies; A is woken by the reply and finishes
#    with the answer. Halfway, the observer disconnects and reconnects with
#    `--after` its last offset: the two tails show every offset once, in order.
# 3. C asks D, which never answers, with a 20 s deadline: C is woken and told the
#    question expired. E, in another request, messages B: the send is rejected.
# 4. Reports each Workflow's history (runs, events, bytes) and A's event batches.
# Afterwards it cancels D. Instructions carry `[script:NAME]` markers for the
# fake model; a real model may ignore them. To run on the fake model, start the
# workers with it first:
#     VLLM_BASE_URL=http://fake-model:8765 make workers-check
#     VLLM_BASE_URL=http://fake-model:8765 make workers-up
# Output files go to OUT_DIR.
set -eu

ENV_FILE=${ENV_FILE:-infra/.env}
export ENV_FILE
CTL=./agentctl
PROFILE=${PROFILE:-default}
OUT=${1:-$(mktemp -d)}
mkdir -p "$OUT"

field() { python3 -c "import json,sys; d=json.load(sys.stdin); print($1)"; }
probe() { PYTHONPATH=. uv run --env-file "$ENV_FILE" python infra/demo/messaging_probe.py "$@"; }
submit() { $CTL task submit --profile "$PROFILE" "$@" 2>/dev/null; }
task_status() { $CTL task status "$1" 2>/dev/null | field "d['task']['status']"; }
offsets() { grep -E '^[0-9]+' "$1" | cut -f1; }
log() { echo "$*" | tee -a "$OUT/demo.txt"; }
until_true() {  # until_true SECONDS WHAT COMMAND...
    limit=$1 what=$2
    shift 2
    i=0
    until "$@"; do
        i=$((i + 1))
        [ "$i" -lt $((limit * 2)) ] || { echo "error: $what after $limit s" >&2; exit 1; }
        sleep 0.5
    done
}
asleep() {  # stops the demo if the task ended instead of waiting
    [ "$(probe sleeping "$1")" = yes ] && return 0
    ended "$1" && { echo "error: $1 ended ($(task_status "$1")) instead of waiting" >&2; exit 1; }
    return 1
}
ended() { s=$(task_status "$1"); [ "$s" != running ] && [ -n "$s" ]; }
asked() { probe messages "$1" | grep -q " ask "; }

# 1. B waits; A asks it.
b_json=$(submit --instructions "[script:demo-answerer] You are the price desk of this request. First call finish_task with status \"waiting\" to wait for questions. When you are woken with a question, look up the price with lookup_price, answer it with send_to_agent using the reply_to value it gives, then call finish_task with status \"done\".")
b=$(echo "$b_json" | field "d['task_id']")
req=$(echo "$b_json" | field "d['request_id']")
log "request: $req"
log "B (price desk): $b"
until_true 300 "B is not waiting" asleep "$b"
log "B is waiting (idle, its Workflow asleep)"

a=$(submit --join "$req" --instructions "[script:demo-asker] Please ask task $b the question \"What is the price of SKU-4?\" with ask_agent, within 600 s (deadline_seconds 600). Then call finish_task with status \"waiting\". When you are woken, call finish_task with status \"done\" and put the answer you were given in the summary." | field "d['task_id']")
log "A (asker): $a"

$CTL tail "$a" > "$OUT/tail-1.log" 2>"$OUT/tail-1.err" &
tail1=$!
until_true 300 "A did not ask" asked "$a"
sleep 2
kill "$tail1" 2>/dev/null || true
wait "$tail1" 2>/dev/null || true
last=$(offsets "$OUT/tail-1.log" | tail -1)
log "observer disconnected after offset $last"

# 2. Reconnect from the last offset and follow A until its Workflow closes.
timeout 900 $CTL tail "$a" --after "$last" > "$OUT/tail-2.log" 2>"$OUT/tail-2.err"
until_true 300 "B did not end" ended "$b"
log "A: $(task_status "$a"), summary: $($CTL task status "$a" 2>/dev/null | field "d['task']['result']['summary']")"
log "B: $(task_status "$b")"
cat "$OUT/tail-1.log" "$OUT/tail-2.log" > "$OUT/tail-all.log"
total=$(offsets "$OUT/tail-all.log" | wc -l)
unique=$(offsets "$OUT/tail-all.log" | sort -n | uniq | wc -l)
top=$(offsets "$OUT/tail-all.log" | sort -n | tail -1)
log "observer saw $total lines, $unique distinct offsets, highest $top (each once and in order: $([ "$total" = "$unique" ] && [ "$unique" = "$top" ] && echo yes || echo no))"

# 3. An unanswered question and a rejected message.
d=$(submit --join "$req" --instructions "[script:demo-silent] This task's only job is to wait; there is no order to process. Do not call any tool except finish_task: call finish_task with status \"waiting\" and the summary \"waiting\" now. If you are woken, call finish_task with status \"waiting\" again. Never answer a question." | field "d['task_id']")
log "D (silent): $d"
until_true 300 "D is not waiting" asleep "$d"
c=$(submit --join "$req" --instructions "[script:demo-asker] Please ask task $d the question \"What is the price of SKU-4?\" with ask_agent, within 20 s (deadline_seconds 20). Then call finish_task with status \"waiting\". When you are woken, call finish_task with status \"done\" and put what you were told in the summary." | field "d['task_id']")
log "C (asks D with a 20 s deadline): $c"
start=$(date +%s)
until_true 300 "C did not end" ended "$c"
log "C: $(task_status "$c") after $(($(date +%s) - start)) s, summary: $($CTL task status "$c" 2>/dev/null | field "d['task']['result']['summary']")"

e_json=$(submit --instructions "[script:demo-outsider] Please tell task $b hi: call send_to_agent with task_id $b and the text \"hi\", then call finish_task with status \"done\".")
e=$(echo "$e_json" | field "d['task_id']")
log "E (another request, $(echo "$e_json" | field "d['request_id']")): $e"
until_true 300 "E did not end" ended "$e"
log "E: $(task_status "$e")"

# 4. Evidence.
probe messages "$a" "$b" "$c" "$d" "$e" | tee "$OUT/messages.txt"
probe history "$a" "$b" "$c" "$d" | tee "$OUT/history.txt"
probe batches "$a" | tee -a "$OUT/demo.txt"

probe cancel "$d" | tee -a "$OUT/demo.txt"
log "output: $OUT"
