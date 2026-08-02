"""SM-2 spaced repetition + ZPD upward nudge.

Per #2 / ADR-0002: SM-2 (Anki-style) per concept — ease factor + interval;
wrong resets the interval, right lengthens it. SM-2 decides *when* a concept
is due; ZPD decides *how hard* the re-ask is (layered on top of SM-2 intervals).
The scheduler nudges difficulty *up* when the user is cruising (high pass rate
at current tier). SR timing wins over interleaving on conflict.

This module is pure logic — no LLM, no I/O. Tests inject grade results directly.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from coach.config import Difficulty, GradeBand

# SM-2 constants (Anki-style)
_EASE_FLOOR = 1.3          # ease never drops below this
_EASE_DELTA_WRONG = 0.2    # ease decreases on wrong
_EASE_DELTA_RIGHT = 0.1    # ease increases on right
_INITIAL_EASE = 2.5
_INTERVAL_LEARNING = 1     # first interval after a wrong answer
_INTERVAL_GRADUATED = 3    # first interval after first correct


@dataclass(frozen=True)
class SRState:
    """The SM-2 state for one concept."""

    ease: float
    interval_days: int
    repetitions: int
    due_date: date
    difficulty: Difficulty
    last_grade_band: GradeBand | None = None


@dataclass(frozen=True)
class SRUpdate:
    """The result of processing a grade through SM-2."""

    new_state: SRState
    is_due: bool


def process_grade(
    state: SRState,
    grade_band: GradeBand,
    today: date,
) -> SRState:
    """Update SM-2 state after a grade.

    - Below/approaching (wrong): reset interval to learning, decrease ease.
    - Meets/exceeds (right): lengthen interval by ease factor, increase ease.
    """
    is_correct = grade_band in (GradeBand.MEETS, GradeBand.EXCEEDS)

    if is_correct:
        new_reps = state.repetitions + 1
        if new_reps == 1:
            new_interval = _INTERVAL_GRADUATED
        else:
            new_interval = max(1, round(state.interval_days * state.ease))
        new_ease = min(_INITIAL_EASE, state.ease + _EASE_DELTA_RIGHT)
    else:
        new_reps = 0
        new_interval = _INTERVAL_LEARNING
        new_ease = max(_EASE_FLOOR, state.ease - _EASE_DELTA_WRONG)

    new_due = today + timedelta(days=new_interval)
    return SRState(
        ease=round(new_ease, 2),
        interval_days=new_interval,
        repetitions=new_reps,
        due_date=new_due,
        difficulty=state.difficulty,
        last_grade_band=grade_band,
    )


def initial_state(difficulty: Difficulty, today: date) -> SRState:
    """Create the initial SR state for a new concept."""
    return SRState(
        ease=_INITIAL_EASE,
        interval_days=0,
        repetitions=0,
        due_date=today,
        difficulty=difficulty,
        last_grade_band=None,
    )


def is_due(state: SRState, today: date) -> bool:
    """True if the concept is due for a re-ask on `today`."""
    return today >= state.due_date


def nudge_difficulty(state: SRState, pass_rate: float) -> Difficulty:
    """ZPD upward nudge — push difficulty up when cruising.

    pass_rate is the fraction of correct answers at the current tier.
    If pass_rate > 0.8 and not already hard, nudge up one tier.
    If pass_rate < 0.3 and not already easy, nudge down one tier.
    Otherwise hold.
    """
    if pass_rate > 0.8 and state.difficulty != Difficulty.HARD:
        order = [Difficulty.EASY, Difficulty.MEDIUM, Difficulty.HARD]
        idx = order.index(state.difficulty)
        return order[min(idx + 1, len(order) - 1)]
    if pass_rate < 0.3 and state.difficulty != Difficulty.EASY:
        order = [Difficulty.EASY, Difficulty.MEDIUM, Difficulty.HARD]
        idx = order.index(state.difficulty)
        return order[max(idx - 1, 0)]
    return state.difficulty
