from concurrent.futures import ThreadPoolExecutor

import pytest
from usage_ledger import UsageLedger


def test_exhaustion_counts_total_once_and_retains_denial():
    ledger = UsageLedger("run", "root", 1, 10)
    first = ledger.ingress("main", 1)
    ledger.settle(first, {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10})
    assert ledger.ingress("main", 2)["denial"] == "token budget"
    assert ledger.totals() == dict(
        ingress=2,
        physical_dispatches=1,
        denied_ingress=1,
        input_tokens=7,
        output_tokens=3,
        unknown_usage=0,
        logical_steps=1,
    )


def test_known_retry_has_two_dispatches_one_logical_step():
    ledger = UsageLedger("run", "root", 1, 10)
    ledger.settle(ledger.ingress("main", 1), None, known_pre_generation=True)
    ledger.settle(ledger.ingress("retry", 1), {"prompt_tokens": 7, "completion_tokens": 3})
    assert not ledger.ingress("main", 2)["dispatched"]
    assert ledger.totals()["physical_dispatches"] == 2
    assert ledger.totals()["logical_steps"] == 1


def test_auxiliary_exhaustion_blocks_main_and_auxiliary():
    ledger = UsageLedger("run", "root", 1, 10)
    ledger.settle(ledger.ingress("compaction", 1), {"prompt_tokens": 4, "completion_tokens": 6})
    assert not ledger.ingress("main", 2)["dispatched"]
    assert not ledger.ingress("compaction", 3)["dispatched"]
    assert ledger.totals()["physical_dispatches"] == 1


def test_unknown_usage_is_not_zero_and_blocks_concurrent_admission():
    ledger = UsageLedger("run", "root", 1, 10)
    with ThreadPoolExecutor(max_workers=8) as pool:
        records = list(pool.map(lambda i: ledger.ingress("main", i), range(20)))
    assert sum(r["dispatched"] for r in records) == 1
    assert ledger.totals()["unknown_usage"] == 1
    assert ledger.totals()["input_tokens"] is None
    assert {r["denial"] for r in records if not r["dispatched"]} == {"unresolved usage"}


@pytest.mark.parametrize(
    "usage",
    [
        dict(prompt_tokens=-1, completion_tokens=2),
        dict(prompt_tokens=True, completion_tokens=0),
        dict(prompt_tokens=0),
        dict(prompt_tokens=0, completion_tokens=1.5),
    ],
)
def test_invalid_usage_keeps_admission_closed(usage):
    ledger = UsageLedger("run", "root", 1, 10)
    record = ledger.ingress("main", 1)
    with pytest.raises(ValueError):
        ledger.settle(record, usage)
    assert ledger.ingress("main", 2)["denial"] == "unresolved usage"


def test_model_steps_do_not_count_retry_twice():
    ledger = UsageLedger("run", "root", 1, 100, steps=2)
    for step in (1, 1, 2):
        ledger.settle(ledger.ingress("main", step), {"prompt_tokens": 1, "completion_tokens": 0})
    assert ledger.ingress("main", 3)["denial"] == "model-step limit"
