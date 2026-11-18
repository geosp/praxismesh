#!/bin/sh
# Phase 02 task 1.2 (plan R5, R6, R8, R11): from the repository's clean commit, with the
# disposable stack (`make up ENV_FILE=spikes/event-transport/stack.env`) up, run from
# spikes/event-transport:  sh measure.sh
# For each measured option: the shared suite 3 times, then the 5-minute load 3 times;
# (at 1bfac67 also Workflow Streams, and one Streams load with roll-over off).
set -eu
OPTIONS=${OPTIONS:-"table"}  # "table streams" at 1bfac67, where Streams still existed
for n in 1 2 3; do
    SPIKE_TRANSPORTS=$(echo "$OPTIONS" | tr ' ' ',') SPIKE_RESULTS="results/run$n" \
        uv run pytest -q -p no:cacheprovider tests/test_suite.py || true
    for option in $OPTIONS; do
        uv run python load.py "$option" --label "run$n"
    done
done
