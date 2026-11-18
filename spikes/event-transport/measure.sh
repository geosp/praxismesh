#!/bin/sh
# Phase 02 task 1.2 (plan R5, R6, R8, R11): from the repository's clean commit, run from
# spikes/event-transport:  sh measure.sh
# Before every run the disposable stack is reset, so no run inherits another's state
# (plan Rollout; impl review F62). Each run is the shared suite, then the 5-minute load,
# for each option. The original Streams and table measurements ran at c1fda62 without
# resets ("table streams", plus one Streams load with roll-over off).
set -eu
OPTIONS=${OPTIONS:-"table"}
LABEL=${LABEL:-open}
ROOT=$(cd ../.. && pwd)
reset() {
    make -C "$ROOT" reset ENV_FILE=spikes/event-transport/stack.env >/dev/null
    make -C "$ROOT" up ENV_FILE=spikes/event-transport/stack.env >/dev/null
}
for n in 1 2 3; do
    for option in $OPTIONS; do
        reset
        SPIKE_TRANSPORTS="$option" SPIKE_RESULTS="results/$LABEL$n" \
            uv run pytest -q -p no:cacheprovider tests/test_suite.py || true
        uv run python load.py "$option" --label "$LABEL$n"
    done
done
