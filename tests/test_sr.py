"""Tests for SM-2 spaced repetition + ZPD nudge — pure logic, no I/O."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from coach.config import Difficulty, GradeBand
from coach.sr import (
    SRState, initial_state, is_due, nudge_difficulty, process_grade,
)


def _state(ease=2.5, interval=3, reps=1, difficulty=Difficulty.MEDIUM,
           due=None, last_band=None) -> SRState:
    return SRState(
        ease=ease, interval_days=interval, repetitions=reps,
        due_date=due or date(2026, 8, 1), difficulty=difficulty,
        last_grade_band=last_band,
    )


class TestProcessGrade:
    def test_correct_lengthens_interval(self):
        state = _state(ease=2.5, interval=3, reps=1)
        new = process_grade(state, GradeBand.MEETS, date(2026, 8, 1))
        # round(3 * 2.5) = 8
        assert new.interval_days == 8
        assert new.repetitions == 2
        assert new.due_date == date(2026, 8, 9)

    def test_wrong_resets_interval(self):
        state = _state(ease=2.5, interval=8, reps=2)
        new = process_grade(state, GradeBand.BELOW, date(2026, 8, 1))
        assert new.interval_days == 1
        assert new.repetitions == 0
        assert new.due_date == date(2026, 8, 2)

    def test_wrong_decreases_ease(self):
        state = _state(ease=2.5)
        new = process_grade(state, GradeBand.BELOW, date(2026, 8, 1))
        assert new.ease == 2.3

    def test_correct_increases_ease(self):
        state = _state(ease=2.3)
        new = process_grade(state, GradeBand.MEETS, date(2026, 8, 1))
        assert new.ease == 2.4

    def test_ease_floor_enforced(self):
        state = _state(ease=1.3)
        new = process_grade(state, GradeBand.BELOW, date(2026, 8, 1))
        assert new.ease == 1.3  # floor

    def test_ease_cap_at_initial(self):
        state = _state(ease=2.5)
        new = process_grade(state, GradeBand.EXCEEDS, date(2026, 8, 1))
        assert new.ease == 2.5  # capped

    def test_first_correct_uses_graduated_interval(self):
        state = _state(ease=2.5, interval=0, reps=0)
        new = process_grade(state, GradeBand.MEETS, date(2026, 8, 1))
        assert new.interval_days == 3
        assert new.repetitions == 1

    def test_exceeds_counts_as_correct(self):
        state = _state(ease=2.5, interval=3, reps=1)
        new = process_grade(state, GradeBand.EXCEEDS, date(2026, 8, 1))
        assert new.repetitions == 2

    def test_approaching_counts_as_wrong(self):
        state = _state(ease=2.5, interval=3, reps=1)
        new = process_grade(state, GradeBand.APPROACHING, date(2026, 8, 1))
        assert new.repetitions == 0
        assert new.interval_days == 1

    def test_last_grade_band_stored(self):
        state = _state()
        new = process_grade(state, GradeBand.MEETS, date(2026, 8, 1))
        assert new.last_grade_band == GradeBand.MEETS


class TestIsDue:
    def test_due_on_due_date(self):
        state = _state(due=date(2026, 8, 5))
        assert is_due(state, date(2026, 8, 5)) is True

    def test_due_after_due_date(self):
        state = _state(due=date(2026, 8, 5))
        assert is_due(state, date(2026, 8, 6)) is True

    def test_not_due_before_due_date(self):
        state = _state(due=date(2026, 8, 5))
        assert is_due(state, date(2026, 8, 4)) is False


class TestInitial:
    def test_initial_state_due_today(self):
        state = initial_state(Difficulty.MEDIUM, date(2026, 8, 1))
        assert state.ease == 2.5
        assert state.interval_days == 0
        assert state.repetitions == 0
        assert state.due_date == date(2026, 8, 1)


class TestZPDNudge:
    def test_high_pass_rate_nudges_up(self):
        state = _state(difficulty=Difficulty.EASY)
        new_diff = nudge_difficulty(state, pass_rate=0.9)
        assert new_diff == Difficulty.MEDIUM

    def test_medium_to_hard_on_high_pass_rate(self):
        state = _state(difficulty=Difficulty.MEDIUM)
        new_diff = nudge_difficulty(state, pass_rate=0.85)
        assert new_diff == Difficulty.HARD

    def test_hard_stays_hard_on_high_pass_rate(self):
        state = _state(difficulty=Difficulty.HARD)
        new_diff = nudge_difficulty(state, pass_rate=0.95)
        assert new_diff == Difficulty.HARD

    def test_low_pass_rate_nudges_down(self):
        state = _state(difficulty=Difficulty.HARD)
        new_diff = nudge_difficulty(state, pass_rate=0.2)
        assert new_diff == Difficulty.MEDIUM

    def test_medium_pass_rate_holds(self):
        state = _state(difficulty=Difficulty.MEDIUM)
        new_diff = nudge_difficulty(state, pass_rate=0.5)
        assert new_diff == Difficulty.MEDIUM
