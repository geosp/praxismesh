#!/bin/sh
# One-shot job: create the Temporal namespace with its retention (plan §4.13).
# An existing namespace is left unchanged; to change its retention, run
# `temporal operator namespace update` (see README). Exits only once the
# namespace can be described, so it is usable when this job reports success.
set -eu

ns=${TEMPORAL_NAMESPACE:-default}
retention=${TEMPORAL_RETENTION:-72h}
export TEMPORAL_ADDRESS=temporal:7233

if temporal operator namespace describe --namespace "$ns" >/dev/null 2>&1; then
    echo "temporal-namespace: ${ns} already exists"
else
    temporal operator namespace create --namespace "$ns" --retention "$retention" ||
        echo "temporal-namespace: create failed or raced; checking it exists"
fi

i=0
until temporal operator namespace describe --namespace "$ns" >/dev/null 2>&1; do
    i=$((i + 1))
    if [ "$i" -ge 30 ]; then
        echo "temporal-namespace: ${ns} is not usable after 30 s" >&2
        exit 1
    fi
    sleep 1
done
echo "temporal-namespace: ${ns} ready"
