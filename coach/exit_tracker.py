"""Exit/kill criterion tracker — surfaces Phase 1 signals in /stats.

Per #8: the exit criterion is named numbers, not "feels fair":
- usage = 8/10 answered days (no >2 consecutive misses) over a 10-day window
- SR = ≥3 re-asks triggered AND ≥1 second-encounter pass
  (high-accuracy exception: pass if re-asks <3 due to high first-try accuracy,
  flag curriculum difficulty for Phase 2)
- fairness = dispute rate ≤20% AND ≥3 disputes AND ≤50% grade-change rate
  (if <3 disputes → inconclusive, manual review + one self-report)
- kill = ≥3 consecutive misses OR engagement trend <50% (last 5 vs first 5)
- SR/grading failure → fix-and-extend 5 days, one chance, second failure → kill
- clock starts day 1 at first answered challenge

This module is pure logic over seeded SQLite state — tests inject data directly.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Literal

from coach.store import Store


@dataclass(frozen=True)
class ExitSignals:
    """The Phase 1 exit/kill signals."""

    usage_pass: bool
    usage_answered_days: int
    usage_consecutive_misses: int

    sr_pass: bool
    sr_re_asks: int
    sr_second_encounter_passes: int
    sr_high_accuracy_exception: bool

    fairness_pass: bool | None  # None = inconclusive
    fairness_dispute_rate: float
    fairness_grade_change_rate: float
    fairness_dispute_count: int

    kill_triggered: bool
    kill_reason: str | None

    fix_and_extend: bool
    fix_and_extend_reason: str | None


def compute_signals(store: Store, today: date) -> ExitSignals:
    """Compute the exit/kill signals from the store's state.

    The clock starts at the first answered challenge (meta key "clock_started").
    """
    clock_started_str = store.get_meta("clock_started")
    if clock_started_str is None:
        # No answered challenges yet — all signals are at initial state
        return ExitSignals(
            usage_pass=False, usage_answered_days=0, usage_consecutive_misses=0,
            sr_pass=False, sr_re_asks=0, sr_second_encounter_passes=0,
            sr_high_accuracy_exception=False,
            fairness_pass=None, fairness_dispute_rate=0.0,
            fairness_grade_change_rate=0.0, fairness_dispute_count=0,
            kill_triggered=False, kill_reason=None,
            fix_and_extend=False, fix_and_extend_reason=None,
        )

    clock_started = date.fromisoformat(clock_started_str)
    window_start = max(clock_started, today - timedelta(days=9))

    # --- Usage: 8/10 answered days, no >2 consecutive misses ---
    answered_days = _count_answered_days(store, window_start, today)
    consecutive_misses = _max_consecutive_misses(store, window_start, today)
    usage_pass = answered_days >= 8 and consecutive_misses <= 2

    # --- SR: ≥3 re-asks AND ≥1 second-encounter pass ---
    re_asks = _count_re_asks(store)
    second_passes = _count_second_encounter_passes(store)
    high_accuracy_exception = re_asks < 3 and _first_try_accuracy_high(store)
    sr_pass = (re_asks >= 3 and second_passes >= 1) or high_accuracy_exception

    # --- Fairness: dispute rate ≤20% AND ≥3 disputes AND ≤50% grade-change ---
    dispute_count = _count_disputes(store)
    total_grades = _count_grades(store)
    dispute_rate = dispute_count / total_grades if total_grades > 0 else 0.0
    grade_changes = _count_grade_changes(store)
    grade_change_rate = grade_changes / dispute_count if dispute_count > 0 else 0.0
    if dispute_count < 3:
        fairness_pass = None  # inconclusive
    else:
        fairness_pass = dispute_rate <= 0.2 and grade_change_rate <= 0.5

    # --- Kill: ≥3 consecutive misses OR engagement trend <50% ---
    kill_reason = None
    if consecutive_misses >= 3:
        kill_reason = "3+ consecutive missed days"
    elif _engagement_trend_below_50(store, window_start, today):
        kill_reason = "engagement trend <50%"
    kill_triggered = kill_reason is not None

    # --- Fix-and-extend: SR/grading failure ---
    fix_and_extend_reason = None
    if _has_sr_failure(store) and not _fix_and_extend_used(store):
        fix_and_extend_reason = "SR/grading failure"
    fix_and_extend = fix_and_extend_reason is not None

    return ExitSignals(
        usage_pass=usage_pass,
        usage_answered_days=answered_days,
        usage_consecutive_misses=consecutive_misses,
        sr_pass=sr_pass,
        sr_re_asks=re_asks,
        sr_second_encounter_passes=second_passes,
        sr_high_accuracy_exception=high_accuracy_exception,
        fairness_pass=fairness_pass,
        fairness_dispute_rate=dispute_rate,
        fairness_grade_change_rate=grade_change_rate,
        fairness_dispute_count=dispute_count,
        kill_triggered=kill_triggered,
        kill_reason=kill_reason,
        fix_and_extend=fix_and_extend,
        fix_and_extend_reason=fix_and_extend_reason,
    )


def _count_answered_days(store: Store, start: date, end: date) -> int:
    """Count days with at least one answered challenge in the window."""
    conn = store._conn
    row = conn.execute(
        "SELECT COUNT(DISTINCT DATE(a.answered_at)) as n FROM answers a "
        "WHERE DATE(a.answered_at) >= ? AND DATE(a.answered_at) <= ?",
        (start.isoformat(), end.isoformat()),
    ).fetchone()
    return row["n"] if row else 0


def _max_consecutive_misses(store: Store, start: date, end: date) -> int:
    """Max consecutive days with no answered challenge in the window."""
    conn = store._conn
    rows = conn.execute(
        "SELECT DISTINCT DATE(a.answered_at) as d FROM answers a "
        "WHERE DATE(a.answered_at) >= ? AND DATE(a.answered_at) <= ? "
        "ORDER BY d",
        (start.isoformat(), end.isoformat()),
    ).fetchall()
    answered_set = {r["d"] for r in rows}
    max_miss = 0
    current_miss = 0
    d = start
    while d <= end:
        if d.isoformat() not in answered_set:
            current_miss += 1
            max_miss = max(max_miss, current_miss)
        else:
            current_miss = 0
        d += timedelta(days=1)
    return max_miss


def _count_re_asks(store: Store) -> int:
    """Count SR re-asks triggered (challenges for concepts that had prior grades)."""
    conn = store._conn
    row = conn.execute(
        "SELECT COUNT(*) as n FROM challenges c "
        "WHERE c.concept_node_id IN ("
        "  SELECT concept_node_id FROM challenges c2 "
        "  JOIN answers a ON a.challenge_id = c2.id "
        "  JOIN grades g ON g.answer_id = a.id "
        "  WHERE c2.id != c.id"
        ")"
    ).fetchone()
    return row["n"] if row else 0


def _count_second_encounter_passes(store: Store) -> int:
    """Count re-asks that passed (meets/exceeds) after a prior grade."""
    conn = store._conn
    row = conn.execute(
        "SELECT COUNT(*) as n FROM grades g "
        "JOIN answers a ON g.answer_id = a.id "
        "JOIN challenges c ON a.challenge_id = c.id "
        "WHERE g.band IN ('meets', 'exceeds') AND g.is_deferred = 0 "
        "AND c.concept_node_id IN ("
        "  SELECT c2.concept_node_id FROM challenges c2 "
        "  JOIN answers a2 ON a2.challenge_id = c2.id "
        "  JOIN grades g2 ON g2.answer_id = a2.id "
        "  WHERE c2.id != c.id AND g2.id < g.id"
        ")"
    ).fetchone()
    return row["n"] if row else 0


def _first_try_accuracy_high(store: Store) -> bool:
    """True if first-try accuracy is high (≥80% of first grades are meets/exceeds)."""
    conn = store._conn
    row = conn.execute(
        "SELECT "
        "  SUM(CASE WHEN band IN ('meets', 'exceeds') THEN 1 ELSE 0 END) as passes, "
        "  COUNT(*) as total "
        "FROM grades WHERE is_deferred = 0"
    ).fetchone()
    if not row or row["total"] == 0:
        return False
    return row["passes"] / row["total"] >= 0.8


def _count_disputes(store: Store) -> int:
    conn = store._conn
    row = conn.execute("SELECT COUNT(*) as n FROM disputes").fetchone()
    return row["n"] if row else 0


def _count_grades(store: Store) -> int:
    conn = store._conn
    row = conn.execute("SELECT COUNT(*) as n FROM grades WHERE is_deferred = 0").fetchone()
    return row["n"] if row else 0


def _count_grade_changes(store: Store) -> int:
    """Count disputes where the resolved grade differs from the original."""
    conn = store._conn
    row = conn.execute(
        "SELECT COUNT(*) as n FROM disputes WHERE resolved_band IS NOT NULL "
        "AND resolved_band != ("
        "  SELECT band FROM grades WHERE id = disputes.grade_id LIMIT 1"
        ")"
    ).fetchone()
    return row["n"] if row else 0


def _engagement_trend_below_50(store: Store, start: date, end: date) -> bool:
    """True if engagement trend (last 5 vs first 5 days) is below 50%."""
    conn = store._conn
    first_half_end = start + timedelta(days=4)
    last_half_start = end - timedelta(days=4)
    first = conn.execute(
        "SELECT COUNT(DISTINCT DATE(a.answered_at)) as n FROM answers a "
        "WHERE DATE(a.answered_at) >= ? AND DATE(a.answered_at) <= ?",
        (start.isoformat(), first_half_end.isoformat()),
    ).fetchone()["n"]
    last = conn.execute(
        "SELECT COUNT(DISTINCT DATE(a.answered_at)) as n FROM answers a "
        "WHERE DATE(a.answered_at) >= ? AND DATE(a.answered_at) <= ?",
        (last_half_start.isoformat(), end.isoformat()),
    ).fetchone()["n"]
    if first == 0:
        return False
    return (last / first) < 0.5


def _has_sr_failure(store: Store) -> bool:
    """Check if there's an SR/grading failure flag."""
    return store.get_meta("sr_failure") == "1"


def _fix_and_extend_used(store: Store) -> bool:
    """Check if fix-and-extend has already been used (one chance)."""
    return store.get_meta("fix_and_extend_used") == "1"
