#!/bin/sh
# One-shot job: make the Temporal namespace exist with the configured retention
# (plan §4.13). Creates it if missing; if it exists with another retention,
# updates the retention. Fails, naming the cause, if Temporal cannot be asked,
# or if create or update fails. Exits only once `namespace describe` shows the
# configured retention.
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

# Prints the namespace's retention in seconds, or "absent" if it does not exist.
# Any other describe error is retried for up to 30 s, then reported.
retention_of_namespace() {
    tries=0
    while :; do
        if out=$(temporal operator namespace describe --namespace "$ns" -o json 2>&1); then
            echo "$out" | sed -n 's/.*"workflowExecutionRetentionTtl": *"\([0-9]*\)s".*/\1/p'
            return 0
        fi
        case "$out" in
        *"is not found"*) echo absent; return 0 ;;
        esac
        tries=$((tries + 1))
        if [ "$tries" -ge 30 ]; then
            echo "temporal-namespace: cannot describe ${ns}: ${out}" >&2
            return 1
        fi
        sleep 1
    done
}

have=$(retention_of_namespace)
if [ "$have" = absent ]; then
    echo "temporal-namespace: creating ${ns} with retention ${retention}"
    if ! temporal operator namespace create --namespace "$ns" --retention "$retention"; then
        # Another run may have created it meanwhile; anything else is a real failure.
        [ "$(retention_of_namespace)" != absent ] || {
            echo "temporal-namespace: creating ${ns} failed (see the error above)" >&2
            exit 1
        }
    fi
elif [ "$have" != "$want" ]; then
    echo "temporal-namespace: ${ns} has retention ${have}s; updating to ${retention}"
    temporal operator namespace update --namespace "$ns" --retention "$retention" || {
        echo "temporal-namespace: updating the retention of ${ns} failed (see the error above)" >&2
        exit 1
    }
else
    echo "temporal-namespace: ${ns} exists with retention ${retention}"
fi

i=0
until [ "$(retention_of_namespace)" = "$want" ]; do
    i=$((i + 1))
    if [ "$i" -ge 30 ]; then
        echo "temporal-namespace: ${ns} does not show retention ${retention} after 30 s" >&2
        exit 1
    fi
    sleep 1
done
echo "temporal-namespace: ${ns} ready (retention ${retention})"
