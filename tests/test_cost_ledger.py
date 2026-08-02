"""Tests for the cost ledger — token math and the fallback ladder."""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from coach.config import ModelName
from coach.cost_ledger import CallRecord, CapStatus, CostLedger, token_cost


class TestTokenCost:
    def test_haiku_basic_cost(self):
        cost = token_cost(ModelName.HAIKU, input_tokens=1000,
                          output_tokens=500)
        # 1000 * 1.00/1M + 500 * 5.00/1M = 0.001 + 0.0025 = 0.0035
        assert cost == pytest.approx(0.0035)

    def test_sonnet_basic_cost(self):
        cost = token_cost(ModelName.SONNET,
                          input_tokens=1000, output_tokens=500)
        # 1000 * 3.00/1M + 500 * 15.00/1M = 0.003 + 0.0075 = 0.0105
        assert cost == pytest.approx(0.0105)

    def test_cache_read_is_tenth_of_input(self):
        cost = token_cost(
            ModelName.SONNET, input_tokens=0, output_tokens=0, cache_read_tokens=10000
        )
        # 10000 * 3.00 * 0.1 / 1M = 0.003
        assert cost == pytest.approx(0.003)


class TestLedgerRecording:
    def test_record_stores_call_with_computed_cost(self):
        ledger = CostLedger(daily_budget=1.0, weekly_budget=10.0)
        rec = ledger.record(
            ModelName.HAIKU, input_tokens=2000, output_tokens=1000, purpose="generate"
        )
        assert rec.model == ModelName.HAIKU
        assert rec.purpose == "generate"
        assert rec.cost_usd == pytest.approx(0.007)
        assert len(ledger.records) == 1

    def test_daily_spend_aggregates_same_day(self):
        ledger = CostLedger(daily_budget=1.0, weekly_budget=10.0)
        day = date(2026, 8, 1)
        ts = datetime.combine(day, datetime.min.time())
        ledger.record(ModelName.HAIKU, 1000, 0, "generate", timestamp=ts)
        ledger.record(ModelName.SONNET, 1000, 0, "grade", timestamp=ts)
        spend = ledger.daily_spend(day)
        assert spend == pytest.approx(0.001 + 0.003)

    def test_weekly_spend_covers_seven_day_window(self):
        ledger = CostLedger(daily_budget=1.0, weekly_budget=10.0)
        today = date(2026, 8, 7)
        for i in range(7):
            d = today - timedelta(days=i)
            ts = datetime.combine(d, datetime.min.time())
            ledger.record(ModelName.HAIKU, 1000, 0, "generate", timestamp=ts)
        # 7 calls * 0.001 = 0.007
        assert ledger.weekly_spend(today) == pytest.approx(0.007)


class TestFallbackLadder:
    def test_no_caps_when_under_budget(self):
        ledger = CostLedger(daily_budget=1.0, weekly_budget=10.0)
        status = ledger.check_caps(date(2026, 8, 1))
        assert status.economy_mode is False
        assert status.skip_regenerator is False
        assert status.skip_new_lesson is False
        assert status.critic_protected is True

    def test_economy_mode_at_80pct_daily(self):
        ledger = CostLedger(daily_budget=1.0, weekly_budget=10.0)
        day = date(2026, 8, 1)
        ts = datetime.combine(day, datetime.min.time())
        # Spend 0.80 → economy mode on
        ledger.record(ModelName.SONNET, 266_667, 0, "grade", timestamp=ts)
        # ~0.80
        status = ledger.check_caps(day)
        assert status.economy_mode is True
        assert status.skip_regenerator is False  # hard cap not hit

    def test_skip_regenerator_at_hard_cap(self):
        ledger = CostLedger(daily_budget=1.0, weekly_budget=10.0)
        day = date(2026, 8, 1)
        ts = datetime.combine(day, datetime.min.time())
        ledger.record(ModelName.SONNET, 333_334, 0, "grade", timestamp=ts)
        # ~1.0 → hard cap
        status = ledger.check_caps(day)
        assert status.skip_regenerator is True
        assert status.economy_mode is True

    def test_skip_new_lesson_at_weekly_cap(self):
        ledger = CostLedger(daily_budget=10.0, weekly_budget=5.0)
        day = date(2026, 8, 7)
        ts = datetime.combine(day, datetime.min.time())
        # Spend 5.0 over the week → weekly cap
        ledger.record(ModelName.SONNET, 1_666_667, 0, "grade", timestamp=ts)
        status = ledger.check_caps(day)
        assert status.skip_new_lesson is True

    def test_critic_never_dropped_under_any_cap(self):
        ledger = CostLedger(daily_budget=0.01, weekly_budget=0.01)
        day = date(2026, 8, 1)
        ts = datetime.combine(day, datetime.min.time())
        ledger.record(ModelName.SONNET, 100_000, 0, "grade", timestamp=ts)
        status = ledger.check_caps(day)
        # All caps hit, but critic stays protected
        assert status.economy_mode is True
        assert status.skip_regenerator is True
        assert status.skip_new_lesson is True
        assert status.critic_protected is True
