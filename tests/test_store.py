"""Tests for the SQLite store — challenge/answer/grade/SR state round-trips."""
from __future__ import annotations

from datetime import date, datetime

import pytest

from coach.config import ChallengeType, Difficulty, GradeBand, ModelName
from coach.store import Store, init_db


@pytest.fixture
def store(tmp_path):
    conn = init_db(tmp_path / "test.db")
    s = Store(conn)
    yield s
    s.close()


class TestChallengeRoundTrip:
    def test_save_and_get_challenge(self, store):
        cid = store.save_challenge(
            "ai-fluency/test", ChallengeType.CONCEPT_RECALL, "What is RAG?",
            "{}", datetime(2026, 8, 1, 7, 0),
        )
        ch = store.get_challenge(cid)
        assert ch["concept_node_id"] == "ai-fluency/test"
        assert ch["challenge_text"] == "What is RAG?"

    def test_get_current_challenge_returns_unanswered(self, store):
        store.save_challenge("a", ChallengeType.SCENARIO, "q1", "{}",
                             datetime(2026, 8, 1, 7))
        store.save_challenge("b", ChallengeType.CONCEPT_RECALL, "q2", "{}",
                             datetime(2026, 8, 2, 7))
        current = store.get_current_challenge()
        assert current["challenge_text"] == "q2"

    def test_mark_answered_clears_current(self, store):
        cid = store.save_challenge("a", ChallengeType.SCENARIO, "q1", "{}",
                                   datetime(2026, 8, 1, 7))
        store.mark_answered(cid, datetime(2026, 8, 1, 12))
        assert store.get_current_challenge() is None


class TestAnswerRoundTrip:
    def test_save_answer_marks_challenge_answered(self, store):
        cid = store.save_challenge("a", ChallengeType.SCENARIO, "q1", "{}",
                                   datetime(2026, 8, 1, 7))
        aid = store.save_answer(cid, "my answer", datetime(2026, 8, 1, 12))
        ans = store.get_answer(aid)
        assert ans["answer_text"] == "my answer"
        assert store.get_current_challenge() is None

    def test_get_ungraded_answers_returns_only_ungraded(self, store):
        cid = store.save_challenge("a", ChallengeType.SCENARIO, "q1", "{}",
                                   datetime(2026, 8, 1, 7))
        aid = store.save_answer(cid, "ans", datetime(2026, 8, 1, 12))
        ungraded = store.get_ungraded_answers()
        assert len(ungraded) == 1
        assert ungraded[0]["answer_text"] == "ans"

        store.save_grade(aid, ModelName.SONNET, GradeBand.MEETS, 2, "ok",
                         "scenario", datetime(2026, 8, 1, 23))
        assert len(store.get_ungraded_answers()) == 0


class TestGradeRoundTrip:
    def test_save_and_get_grade(self, store):
        cid = store.save_challenge("a", ChallengeType.SCENARIO, "q1", "{}",
                                   datetime(2026, 8, 1, 7))
        aid = store.save_answer(cid, "ans", datetime(2026, 8, 1, 12))
        gid = store.save_grade(aid, ModelName.SONNET, GradeBand.MEETS, 2,
                               "good", "scenario", datetime(2026, 8, 1, 23))
        grades = store.get_grades_for_answer(aid)
        assert len(grades) == 1
        assert grades[0]["band"] == "meets"
        assert grades[0]["score"] == 2

    def test_get_latest_grade_skips_deferred(self, store):
        cid = store.save_challenge("a", ChallengeType.SCENARIO, "q1", "{}",
                                   datetime(2026, 8, 1, 7))
        aid = store.save_answer(cid, "ans", datetime(2026, 8, 1, 12))
        store.save_grade(aid, ModelName.SONNET, GradeBand.BELOW, 0,
                         "deferred", "scenario", datetime(2026, 8, 1, 23),
                         is_deferred=True)
        store.save_grade(aid, ModelName.SONNET, GradeBand.MEETS, 2,
                         "resolved", "scenario", datetime(2026, 8, 2, 23))
        latest = store.get_latest_grade(aid)
        assert latest["band"] == "meets"

    def test_get_latest_grade_overall_returns_most_recent(self, store):
        """get_latest_grade_overall returns the most recent non-deferred grade
        across ALL answers — not filtered by answer_id. Needed for /stats (#41)."""
        cid1 = store.save_challenge("a", ChallengeType.SCENARIO, "q1", "{}",
                                    datetime(2026, 8, 1, 7))
        aid1 = store.save_answer(cid1, "ans1", datetime(2026, 8, 1, 12))
        store.save_grade(aid1, ModelName.SONNET, GradeBand.MEETS, 2,
                         "first grade", "scenario", datetime(2026, 8, 1, 23))
        cid2 = store.save_challenge("b", ChallengeType.CONCEPT_RECALL, "q2", "{}",
                                    datetime(2026, 8, 2, 7))
        aid2 = store.save_answer(cid2, "ans2", datetime(2026, 8, 2, 12))
        store.save_grade(aid2, ModelName.SONNET, GradeBand.EXCEEDS, 3,
                         "second grade", "concept-recall",
                         datetime(2026, 8, 2, 23))
        latest = store.get_latest_grade_overall()
        assert latest is not None
        assert latest["feedback"] == "second grade"

    def test_get_latest_grade_overall_skips_deferred(self, store):
        """get_latest_grade_overall skips deferred grades (#6 flag-and-defer)."""
        cid = store.save_challenge("a", ChallengeType.SCENARIO, "q1", "{}",
                                   datetime(2026, 8, 1, 7))
        aid = store.save_answer(cid, "ans", datetime(2026, 8, 1, 12))
        store.save_grade(aid, ModelName.SONNET, GradeBand.BELOW, 0,
                         "deferred", "scenario", datetime(2026, 8, 1, 23),
                         is_deferred=True)
        latest = store.get_latest_grade_overall()
        assert latest is None

    def test_get_latest_grade_overall_returns_none_when_empty(self, store):
        assert store.get_latest_grade_overall() is None

    def test_get_latest_grade_overall_skips_critic_grade(self, store):
        """get_latest_grade_overall skips critic grades even if non-deferred
        (defense in depth — the critic re-grades; only the grader's resolved
        grade is user-facing)."""
        cid = store.save_challenge("a", ChallengeType.SCENARIO, "q1", "{}",
                                   datetime(2026, 8, 1, 7))
        aid = store.save_answer(cid, "ans", datetime(2026, 8, 1, 12))
        store.save_grade(aid, ModelName.SONNET, GradeBand.BELOW, 0,
                         "critic says fail", "scenario", datetime(2026, 8, 1, 23),
                         is_critic=True, is_deferred=False)
        assert store.get_latest_grade_overall() is None


class TestSRState:
    def test_upsert_and_get_sr_state(self, store):
        store.upsert_sr_state("ai-fluency/test", 2.5, 3, 1,
                              date(2026, 8, 4), Difficulty.MEDIUM)
        state = store.get_sr_state("ai-fluency/test")
        assert state["ease"] == 2.5
        assert state["interval_days"] == 3
        assert state["due_date"] == "2026-08-04"

    def test_upsert_overwrites_existing(self, store):
        store.upsert_sr_state("a", 2.5, 3, 1, date(
            2026, 8, 4), Difficulty.MEDIUM)
        store.upsert_sr_state("a", 2.3, 7, 2, date(
            2026, 8, 11), Difficulty.HARD)
        state = store.get_sr_state("a")
        assert state["ease"] == 2.3
        assert state["interval_days"] == 7


class TestMeta:
    def test_set_and_get_meta(self, store):
        store.set_meta("clock_started", "2026-08-01")
        assert store.get_meta("clock_started") == "2026-08-01"

    def test_get_meta_missing_returns_none(self, store):
        assert store.get_meta("nonexistent") is None


class TestDisputes:
    def test_save_and_resolve_dispute(self, store):
        cid = store.save_challenge("a", ChallengeType.SCENARIO, "q1", "{}",
                                   datetime(2026, 8, 1, 7))
        aid = store.save_answer(cid, "ans", datetime(2026, 8, 1, 12))
        gid = store.save_grade(aid, ModelName.SONNET, GradeBand.BELOW, 0,
                               "bad", "scenario", datetime(2026, 8, 1, 23))
        did = store.save_dispute(gid, "I disagree", datetime(2026, 8, 2, 8))
        store.resolve_dispute(did, GradeBand.MEETS, datetime(2026, 8, 2, 9))
