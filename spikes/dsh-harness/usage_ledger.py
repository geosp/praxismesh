"""Trusted, serialized physical-provider admission and usage ledger for the spike."""

from __future__ import annotations

import threading


class UsageLedger:
    def __init__(self, run: str, session: str, attempt: int, budget: int, steps: int = 8):
        if type(budget) is not int or budget <= 0 or type(steps) is not int or steps <= 0:
            raise ValueError("positive integer budgets required")
        self.identity = {"run": run, "session": session, "activity_attempt": attempt}
        self.budget, self.steps = budget, steps
        self.records: list[dict] = []
        self.lock = threading.Lock()

    def ingress(self, purpose: str, logical_step: int) -> dict:
        with self.lock:
            unsettled = any(r["dispatched"] and r["disposition"] == "unknown" for r in self.records)
            tokens = sum(
                (r.get("input_tokens") or 0) + (r.get("output_tokens") or 0) for r in self.records
            )
            logical_steps = {r["logical_step"] for r in self.records if r["dispatched"]}
            reason = (
                "unresolved usage"
                if unsettled
                else "token budget"
                if tokens >= self.budget
                else "model-step limit"
                if logical_step not in logical_steps and len(logical_steps) >= self.steps
                else None
            )
            record = dict(
                self.identity,
                sequence=len(self.records) + 1,
                request_id=f"physical-{len(self.records) + 1:04d}",
                purpose=purpose,
                logical_step=logical_step,
                dispatched=reason is None,
                denial=reason,
                disposition="unknown" if reason is None else "denied",
            )
            self.records.append(record)
            return record

    def settle(
        self,
        record: dict,
        usage: dict | None,
        *,
        known_pre_generation: bool = False,
        cancelled: bool = False,
    ):
        with self.lock:
            if (
                not any(record is item for item in self.records)
                or not record["dispatched"]
                or record["disposition"] != "unknown"
            ):
                raise ValueError("not an unsettled physical dispatch")
            if known_pre_generation:
                if usage is not None:
                    raise ValueError("pre-generation failure cannot also report generated usage")
                record.update(
                    input_tokens=0,
                    output_tokens=0,
                    disposition="pre-generation cancellation"
                    if cancelled
                    else "pre-generation failure",
                )
                return
            if usage is None:
                return  # remains explicitly unknown and blocks further admission
            incoming, outgoing = usage.get("prompt_tokens"), usage.get("completion_tokens")
            if any(type(value) is not int or value < 0 for value in (incoming, outgoing)):
                raise ValueError("authoritative nonnegative integer usage required")
            record.update(input_tokens=incoming, output_tokens=outgoing, disposition="success")

    def totals(self) -> dict:
        with self.lock:
            dispatched = [r for r in self.records if r["dispatched"]]
            unknown = sum(r["disposition"] == "unknown" for r in dispatched)
            return {
                "ingress": len(self.records),
                "physical_dispatches": len(dispatched),
                "denied_ingress": len(self.records) - len(dispatched),
                "input_tokens": None if unknown else sum(r["input_tokens"] for r in dispatched),
                "output_tokens": None if unknown else sum(r["output_tokens"] for r in dispatched),
                "unknown_usage": unknown,
                "logical_steps": len({r["logical_step"] for r in dispatched}),
            }
