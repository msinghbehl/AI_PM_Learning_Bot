"""Cost ledger — logs every API call and triggers the fallback ladder on caps.

Per #5: every call logs model + tokens + cost. Daily/weekly budget caps trigger
fallback: Sonnet→Haiku at soft cap + economy notice; skip regenerator/integrator
at hard cap; skip new-lesson gen at weekly cap; never silently drop the critic.

The ledger is the single source of truth for spend. It is pure logic over an
in-memory record list (tests inject records directly); persistence to SQLite
is the caller's responsibility.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Literal

from coach.config import ModelName

# Per-million-token prices (USD) — Anthropic direct, per research/0001.
# (input, output) per model. Cache-read is 0.1× input.
_PRICE_PER_M: dict[ModelName, tuple[float, float]] = {
    ModelName.HAIKU: (1.00, 5.00),
    ModelName.SONNET: (3.00, 15.00),
    ModelName.OPUS: (5.00, 25.00),
}


def token_cost(
    model: ModelName,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
) -> float:
    """Compute the USD cost of one call."""
    in_price, out_price = _PRICE_PER_M[model]
    return (
        (input_tokens * in_price / 1_000_000)
        + (output_tokens * out_price / 1_000_000)
        + (cache_read_tokens * in_price * 0.1 / 1_000_000)
    )


@dataclass(frozen=True)
class CallRecord:
    """One logged API call."""

    model: ModelName
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cost_usd: float
    purpose: str  # "generate" | "grade" | "critic" | "regenerator" | "integrator"
    timestamp: datetime
    day: date  # for daily/weekly aggregation


@dataclass
class CapStatus:
    """The fallback-ladder decision for the current spend state."""

    economy_mode: bool = False          # soft cap hit → Sonnet→Haiku
    skip_regenerator: bool = False      # hard cap → skip regenerator/integrator
    skip_new_lesson: bool = False       # weekly cap → skip new-lesson gen
    critic_protected: bool = True        # critic is NEVER dropped


class CostLedger:
    """In-memory cost ledger with cap-triggered fallback ladder.

    Call `record()` after each API call; call `check_caps()` before routing to
    decide which tiers/purposes are still allowed.
    """

    def __init__(self, daily_budget: float, weekly_budget: float) -> None:
        self.daily_budget = daily_budget
        self.weekly_budget = weekly_budget
        self._records: list[CallRecord] = []

    def record(
        self,
        model: ModelName,
        input_tokens: int,
        output_tokens: int,
        purpose: str,
        cache_read_tokens: int = 0,
        timestamp: datetime | None = None,
    ) -> CallRecord:
        """Log one call and return the record."""
        ts = timestamp or datetime.now()
        cost = token_cost(model, input_tokens,
                          output_tokens, cache_read_tokens)
        rec = CallRecord(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read_tokens,
            cost_usd=cost,
            purpose=purpose,
            timestamp=ts,
            day=ts.date(),
        )
        self._records.append(rec)
        return rec

    def daily_spend(self, day: date | None = None) -> float:
        """Total spend for a given day (default: today)."""
        target = day or datetime.now().date()
        return sum(r.cost_usd for r in self._records if r.day == target)

    def weekly_spend(self, day: date | None = None) -> float:
        """Total spend for the 7-day window ending on `day` (default: today)."""
        target = day or datetime.now().date()
        start = target - timedelta(days=6)
        return sum(r.cost_usd for r in self._records if start <= r.day <= target)

    def check_caps(self, day: date | None = None) -> CapStatus:
        """Return the fallback-ladder decision for the current spend state.

        - Soft cap (daily): economy mode → Sonnet→Haiku for non-critic calls.
        - Hard cap (daily): skip regenerator/integrator; critic stays.
        - Weekly cap: skip new-lesson generation; critic stays.
        - The critic is never silently dropped under any cap.
        """
        target = day or datetime.now().date()
        daily = self.daily_spend(target)
        weekly = self.weekly_spend(target)

        return CapStatus(
            economy_mode=daily >= self.daily_budget * 0.8,
            skip_regenerator=daily >= self.daily_budget,
            skip_new_lesson=weekly >= self.weekly_budget,
            critic_protected=True,  # never dropped
        )

    @property
    def records(self) -> list[CallRecord]:
        return list(self._records)
