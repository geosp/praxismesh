"""Gateway usage ledger for one DSH attempt (DSH migration plan D2, D9, R11-R13).

Every model request is admitted here before dispatch and settled after. A row is
written durably before dispatch (`LedgerStore.dispatch`), so a request whose
response was never seen stays visible to the next attempt, which charges it
conservatively (D9) instead of treating it as zero.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Protocol

# Per-request output cap in the DSH composition; with the template's
# context_window it bounds what an unobserved request can have used (D9).
DSH_MAX_OUTPUT_TOKENS = 2048


class LedgerStore(Protocol):
    async def dispatch(
        self, task_id: str, turn: int, attempt: int, request_id: str, purpose: str
    ) -> None: ...

    async def settle(
        self,
        task_id: str,
        turn: int,
        attempt: int,
        request_id: str,
        input_tokens: int,
        output_tokens: int,
    ) -> None: ...


@dataclass
class Dispatch:
    request_id: str
    purpose: str
    logical_step: int
    dispatched: bool
    denial: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    settled: bool = False


def unknown_charge(requests: int, context_window: int) -> tuple[int, int]:
    """(input, output) tokens charged for requests whose usage was never observed."""
    return requests * context_window, requests * DSH_MAX_OUTPUT_TOKENS


class UsageLedger:
    """Admission and usage for one attempt. `budget` is the tokens this attempt may
    still spend; `steps` is the template's inner-turn ceiling."""

    def __init__(
        self, store: LedgerStore, task_id: str, turn: int, attempt: int, budget: int, steps: int
    ) -> None:
        if budget <= 0 or steps <= 0:
            raise ValueError("budget and step ceiling must be positive")
        self.store, self.key = store, (task_id, turn, attempt)
        self.budget, self.steps = budget, steps
        self.records: list[Dispatch] = []
        self.lock = asyncio.Lock()

    async def admit(self, purpose: str, logical_step: int, deny: str | None = None) -> Dispatch:
        """Decide one request. A denial is recorded and never dispatched; an admitted
        request is written durably before the caller sends it."""
        async with self.lock:
            sent = [r for r in self.records if r.dispatched]
            used = sum((r.input_tokens or 0) + (r.output_tokens or 0) for r in sent)
            steps = {r.logical_step for r in sent}
            reason = deny or (
                "unresolved usage"
                if any(not r.settled for r in sent)
                else "token budget"
                if used >= self.budget
                else "model-step limit"
                if logical_step not in steps and len(steps) >= self.steps
                else None
            )
            record = Dispatch(
                request_id=f"req-{len(self.records) + 1:04d}",
                purpose=purpose,
                logical_step=logical_step,
                dispatched=reason is None,
                denial=reason,
            )
            if record.dispatched:
                await self.store.dispatch(*self.key, record.request_id, purpose)
            self.records.append(record)
            return record

    async def settle(
        self, record: Dispatch, usage: dict[str, Any] | None, *, known_zero: bool = False
    ) -> None:
        """Record a response's usage. `known_zero` is for a failure proven to precede
        generation. With neither, the request stays unknown and blocks admission."""
        async with self.lock:
            if not record.dispatched or record.settled:
                raise ValueError("not an unsettled dispatch")
            incoming: Any = 0
            outgoing: Any = 0
            if not known_zero:
                if usage is None:
                    return
                incoming, outgoing = usage.get("prompt_tokens"), usage.get("completion_tokens")
                if any(type(v) is not int or v < 0 for v in (incoming, outgoing)):
                    raise ValueError("usage needs nonnegative integer token counts")
            await self.store.settle(*self.key, record.request_id, incoming, outgoing)
            record.input_tokens, record.output_tokens, record.settled = incoming, outgoing, True

    def settled(self) -> dict[str, int]:
        """Usage observed so far; an in-flight request never hides settled tokens."""
        sent = [r for r in self.records if r.dispatched]
        known = [r for r in sent if r.settled]
        return {
            "input_tokens": sum(r.input_tokens or 0 for r in known),
            "output_tokens": sum(r.output_tokens or 0 for r in known),
            "unknown_usage": len(sent) - len(known),
            "logical_steps": len({r.logical_step for r in sent}),
        }

    def denials(self) -> list[str]:
        return [r.denial for r in self.records if r.denial]
