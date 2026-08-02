"""Tests for the grader — rubric loading and rubric-anchored grading."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from coach.call_llm import CallLLM
from coach.config import ChallengeType, GradeBand, ModelName
from coach.cost_ledger import CostLedger
from coach.grader import GradeResult, Grader, Rubric, load_rubric


class FakeClient:
    def __init__(self, response_text: str) -> None:
        self._response = response_text
        self.calls: list = []

    def complete(self, model, system, messages, max_tokens):
        self.calls.append((model, system, messages, max_tokens))
        return (self._response, 100, 50, 0)


def _make_wrapper(response_text: str) -> CallLLM:
    client = FakeClient(response_text)
    ledger = CostLedger(daily_budget=1.0, weekly_budget=10.0)
    return CallLLM(client, ledger)


class TestLoadRubric:
    def test_loads_base_rubric(self, tmp_path):
        base = {
            "version": 1, "challenge_type": "_base", "max_score": 3,
            "scale": [{"label": "below", "score": 0}],
        }
        (tmp_path / "_base.yaml").write_text(yaml.safe_dump(base))
        rubric = load_rubric(ChallengeType.CONCEPT_RECALL, tmp_path)
        assert rubric.max_score == 3
        assert rubric.rubric_id == "concept-recall"

    def test_loads_type_criteria(self, tmp_path):
        base = {
            "version": 1, "challenge_type": "_base", "max_score": 3,
            "scale": [{"label": "below", "score": 0}],
        }
        type_rubric = {
            "version": 1, "challenge_type": "concept-recall", "max_score": 3,
            "criteria": [{"id": "accuracy", "description": "correct", "weight": 2}],
        }
        (tmp_path / "_base.yaml").write_text(yaml.safe_dump(base))
        (tmp_path / "concept-recall.yaml").write_text(yaml.safe_dump(type_rubric))
        rubric = load_rubric(ChallengeType.CONCEPT_RECALL, tmp_path)
        assert len(rubric.criteria) == 1
        assert rubric.criteria[0]["id"] == "accuracy"

    def test_no_type_file_uses_base_only(self, tmp_path):
        base = {
            "version": 1, "challenge_type": "_base", "max_score": 3,
            "scale": [{"label": "below", "score": 0}],
        }
        (tmp_path / "_base.yaml").write_text(yaml.safe_dump(base))
        rubric = load_rubric(ChallengeType.SCENARIO, tmp_path)
        assert rubric.criteria == []


class TestGrader:
    def test_grade_returns_band_score_feedback(self):
        good = json.dumps({"band": "meets", "score": 2,
                          "feedback": "good answer"})
        wrapper = _make_wrapper(good)
        grader = Grader(wrapper, Path("rubrics"))
        result = grader.grade(
            "What is RAG?", ChallengeType.CONCEPT_RECALL, "my answer")
        assert result.band == GradeBand.MEETS
        assert result.score == 2
        assert result.feedback == "good answer"
        assert result.rubric_id == "concept-recall"

    def test_grade_uses_sonnet(self):
        good = json.dumps({"band": "meets", "score": 2, "feedback": "ok"})
        client = FakeClient(good)
        ledger = CostLedger(daily_budget=1.0, weekly_budget=10.0)
        wrapper = CallLLM(client, ledger)
        grader = Grader(wrapper, Path("rubrics"))
        grader.grade("q", ChallengeType.SCENARIO, "a")
        assert client.calls[0][0] == ModelName.SONNET

    def test_grade_includes_rubric_in_prompt(self):
        good = json.dumps({"band": "meets", "score": 2, "feedback": "ok"})
        client = FakeClient(good)
        ledger = CostLedger(daily_budget=1.0, weekly_budget=10.0)
        wrapper = CallLLM(client, ledger)
        grader = Grader(wrapper, Path("rubrics"))
        grader.grade("What is RAG?", ChallengeType.CONCEPT_RECALL, "my answer")
        user_msg = client.calls[0][2][0]["content"]
        assert "Rubric" in user_msg
        assert "concept-recall" in user_msg

    def test_grade_invalid_band_raises(self):
        bad = json.dumps({"band": "excellent", "score": 5, "feedback": "x"})
        wrapper = _make_wrapper(bad)
        grader = Grader(wrapper, Path("rubrics"))
        with pytest.raises(ValueError, match="invalid band"):
            grader.grade("q", ChallengeType.SCENARIO, "a")
