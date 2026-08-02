"""Tests for the exit/kill criterion tracker — seeded SQLite state."""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from coach.config import ChallengeType, Difficulty, GradeBand, ModelName
from coach.exit_tracker import ExitSignals, compute_signals
from coach.store import Store, init_db


@pytest.fixture
def store(tmp_path):
    conn = init_db(tmp_path / "test.db")
    s = Store(conn)
    yield s
    s.close()


def _seed_answer(store, day, concept="a", band=GradeBand.MEETS, score=2):
    """Seed a challenge + answer + grade for a given day."""
    ts = datetime.combine(day, datetime.min.time())
    cid = store.save_challenge(concept, ChallengeType.CONCEPT_RECALL, "q", "{}", ts)
    aid = store.save_answer(cid, "ans", ts)
    store.save_grade(aid, ModelName.SONNET, band, score, "f", "concept-recall", ts)
    return aid


class TestNoClockStarted:
    def test_no_clock_returns_initial_state(self, store):
        signals = compute_signals(store, date(2026, 8, 10))
        assert signals.usage_answered_days == 0
        assert signals.kill_triggered is False
        assert signals.fairness_pass is None


class TestUsage:
    def test_eight_answered_days_passes(self, store):
        store.set_meta("clock_started", "2026-08-01")
        for i in range(8):
            _seed_answer(store, date(2026, 8, 1 + i))
        signals = compute_signals(store, date(2026, 8, 10))
        assert signals.usage_answered_days == 8
        assert signals.usage_pass is True

    def test_three_consecutive_misses_triggers_kill(self, store):
        store.set_meta("clock_started", "2026-08-01")
        for i in range(7):
            _seed_answer(store, date(2026, 8, 1 + i))
        # 3 consecutive misses at the end (days 8, 9, 10)
        signals = compute_signals(store, date(2026, 8, 10))
        assert signals.usage_consecutive_misses >= 3
        assert signals.kill_triggered is True
        assert "consecutive" in signals.kill_reason


class TestFairness:
    def test_under_three_disputes_is_inconclusive(self, store):
        store.set_meta("clock_started", "2026-08-01")
        _seed_answer(store, date(2026, 8, 1))
        signals = compute_signals(store, date(2026, 8, 10))
        assert signals.fairness_pass is None  # inconclusive

    def test_three_disputes_low_rate_passes(self, store):
        store.set_meta("clock_started", "2026-08-01")
        for i in range(10):
            _seed_answer(store, date(2026, 8, 1 + i))
        # Add 3 disputes with no grade changes (resolved to same band)
        for i in range(3):
            aid = _seed_answer(store, date(2026, 8, 11 + i))
            grades = store.get_grades_for_answer(aid)
            gid = grades[0]["id"]
            did = store.save_dispute(gid, "reason", datetime(2026, 8, 11 + i))
            # Resolve to the same band (no grade change)
            store.resolve_dispute(did, GradeBand.MEETS, datetime(2026, 8, 11 + i))
        signals = compute_signals(store, date(2026, 8, 20))
        assert signals.fairness_dispute_count >= 3
        # With 3 disputes and 0 grade changes, rate is 0% which is ≤50%
        assert signals.fairness_grade_change_rate <= 0.5


class TestFixAndExtend:
    def test_sr_failure_triggers_fix_and_extend(self, store):
        store.set_meta("clock_started", "2026-08-01")
        store.set_meta("sr_failure", "1")
        signals = compute_signals(store, date(2026, 8, 10))
        assert signals.fix_and_extend is True
        assert "SR/grading failure" in signals.fix_and_extend_reason

    def test_fix_and_extend_not_triggered_twice(self, store):
        store.set_meta("clock_started", "2026-08-01")
        store.set_meta("sr_failure", "1")
        store.set_meta("fix_and_extend_used", "1")
        signals = compute_signals(store, date(2026, 8, 10))
        assert signals.fix_and_extend is False
