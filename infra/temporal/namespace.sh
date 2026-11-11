#!/bin/sh
# One-shot job: make the Temporal namespace exist with the configured retention
# (plan §4.13). Creates it if missing; if it exists with another retention,
# updates the retention. Fails, naming the cause, if create or update fails.
# Exits only once `namespace describe` shows the configured retention.
set -eu

ns=${TEMPORAL_NAMESPACE:-default}
retention=${TEMPORAL_RETENTION:-72h}
export TEMPORAL_ADDRESS=temporal:7233

# TEMPORAL_RETENTION is <number><s|m|h|d> (checked by infra/check-prereqs.sh).
num=${retention%?}
case "$retention" in
*s) want=$num ;;
*m) want=$((num * 60)) ;;
*h) want=$((num * 3600)) ;;
*d) want=$((num * 86400)) ;;
*)
    echo "temporal-namespace: TEMPORAL_RETENTION '${retention}' is not <number><s|m|h|d>" >&2
    exit 1
    ;;
esac

current_ttl() {
    temporal operator namespace describe --namespace "$ns" -o json 2>/dev/null |
        sed -n 's/.*"workflowExecutionRetentionTtl": *"\([0-9]*\)s".*/\1/p'
}

have=$(current_ttl || true)
if [ -z "$have" ]; then
    echo "temporal-namespace: creating ${ns} with retention ${retention}"
    if ! temporal operator namespace create --namespace "$ns" --retention "$retention"; then
        # Another run may have created it meanwhile; anything else is a real failure.
        have=$(current_ttl || true)
        [ -n "$have" ] || {
            echo "temporal-namespace: creating ${ns} failed" >&2
            exit 1
        }
    fi
elif [ "$have" != "$want" ]; then
    echo "temporal-namespace: ${ns} has retention ${have}s; updating to ${retention}"
    temporal operator namespace update --namespace "$ns" --retention "$retention" || {
        echo "temporal-namespace: updating the retention of ${ns} failed" >&2
        exit 1
    }
else
    echo "temporal-namespace: ${ns} exists with retention ${retention}"
fi

i=0
until [ "$(current_ttl || true)" = "$want" ]; do
    i=$((i + 1))
    if [ "$i" -ge 30 ]; then
        echo "temporal-namespace: ${ns} does not show retention ${retention} after 30 s" >&2
        exit 1
    fi
    sleep 1
done
echo "temporal-namespace: ${ns} ready (retention ${retention})"
