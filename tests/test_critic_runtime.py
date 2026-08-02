"""Tests for the critic — re-grade agreement and disagreement deferral."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from coach.call_llm import CallLLM
from coach.config import ChallengeType, GradeBand, ModelName
from coach.cost_ledger import CostLedger
from coach.critic import Critic, _band_to_int
from coach.grader import GradeResult, Grader


class FakeClient:
    def __init__(self, response_text: str) -> None:
        self._response = response_text

    def complete(self, model, system, messages, max_tokens):
        return (self._response, 100, 50, 0)


def _make_grader(response_text: str) -> Grader:
    client = FakeClient(response_text)
    ledger = CostLedger(daily_budget=1.0, weekly_budget=10.0)
    wrapper = CallLLM(client, ledger)
    return Grader(wrapper, Path("rubrics"))


def _make_grade(band: GradeBand, score: int) -> GradeResult:
    return GradeResult(
        band=band, score=score, feedback="test", rubric_id="concept-recall",
        model=ModelName.SONNET,
    )


class TestBandToInt:
    def test_below_is_0(self):
        assert _band_to_int(GradeBand.BELOW) == 0

    def test_exceeds_is_3(self):
        assert _band_to_int(GradeBand.EXCEEDS) == 3


class TestCriticAgreement:
    def test_same_band_agrees(self):
        good = json.dumps({"band": "meets", "score": 2, "feedback": "ok"})
        grader = _make_grader(good)
        critic = Critic(grader)
        original = _make_grade(GradeBand.MEETS, 2)
        result = critic.review(
            "q", ChallengeType.CONCEPT_RECALL, "a", original)
        assert result.agrees is True
        assert result.band_delta == 0

    def test_exceeds_vs_meets_agrees_within_one_band(self):
        good = json.dumps({"band": "exceeds", "score": 3, "feedback": "great"})
        grader = _make_grader(good)
        critic = Critic(grader)
        original = _make_grade(GradeBand.MEETS, 2)
        result = critic.review(
            "q", ChallengeType.CONCEPT_RECALL, "a", original)
        assert result.band_delta == 1
        assert result.agrees is False  # ≥1-band disagreement


class TestCriticDisagreement:
    def test_two_band_gap_flags(self):
        good = json.dumps({"band": "exceeds", "score": 3, "feedback": "great"})
        grader = _make_grader(good)
        critic = Critic(grader)
        original = _make_grade(GradeBand.BELOW, 0)
        result = critic.review(
            "q", ChallengeType.CONCEPT_RECALL, "a", original)
        assert result.band_delta == 3
        assert result.agrees is False

    def test_critic_grade_returned(self):
        good = json.dumps(
            {"band": "approaching", "score": 1, "feedback": "weak"})
        grader = _make_grader(good)
        critic = Critic(grader)
        original = _make_grade(GradeBand.MEETS, 2)
        result = critic.review(
            "q", ChallengeType.CONCEPT_RECALL, "a", original)
        assert result.critic_grade.band == GradeBand.APPROACHING
        assert result.band_delta == 1
