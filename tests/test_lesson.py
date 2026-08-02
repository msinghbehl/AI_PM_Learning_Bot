"""Tests for the lesson generator — rotation, cold questions, mission-grounded."""
from __future__ import annotations

import json

import pytest

from coach.call_llm import CallLLM
from coach.config import ChallengeType, ModelName
from coach.cost_ledger import CostLedger
from coach.curriculum import CurriculumNode
from coach.lesson import Lesson, LessonGenerator


class FakeClient:
    def __init__(self, response_text: str) -> None:
        self._response = response_text
        self.calls: list = []

    def complete(self, model, system, messages, max_tokens):
        self.calls.append((model, system, messages, max_tokens))
        return (self._response, 100, 50, 0)


def _make_node(id_: str = "ai-fluency/test", **kw) -> CurriculumNode:
    from coach.config import Difficulty
    defaults = dict(
        id=id_, gap="AI technical fluency", concept="Test concept",
        difficulty=Difficulty.MEDIUM,
        source=[{"url": "https://example.com", "type": "report"}],
        related_gaps=[], prerequisites=[],
        challenge_types=["concept-recall"], phase=1,
    )
    defaults.update(kw)
    return CurriculumNode(**defaults)


def _make_wrapper(response_text: str) -> tuple[CallLLM, FakeClient]:
    client = FakeClient(response_text)
    ledger = CostLedger(daily_budget=1.0, weekly_budget=10.0)
    return CallLLM(client, ledger), client


class TestRotation:
    def test_challenge_type_rotates_three_formats(self):
        wrapper, _ = _make_wrapper(json.dumps({
            "pm_concept": "p", "ai_concept": "a", "challenge": "c"}))
        gen = LessonGenerator(wrapper, [_make_node()])
        types = [gen.next_challenge_type() for _ in range(6)]
        assert types[0] == ChallengeType.CONCEPT_RECALL
        assert types[1] == ChallengeType.SCENARIO
        assert types[2] == ChallengeType.TECHNICAL_DEEP_DIVE
        assert types[3] == ChallengeType.CONCEPT_RECALL  # cycles

    def test_node_rotates_through_curriculum(self):
        wrapper, _ = _make_wrapper(json.dumps({
            "pm_concept": "p", "ai_concept": "a", "challenge": "c"}))
        nodes = [_make_node("ai-fluency/a"), _make_node("ai-fluency/b")]
        gen = LessonGenerator(wrapper, nodes)
        assert gen.next_node().id == "ai-fluency/a"
        assert gen.next_node().id == "ai-fluency/b"
        assert gen.next_node().id == "ai-fluency/a"  # cycles


class TestGenerate:
    def test_generates_lesson_with_all_three_parts(self):
        good = json.dumps({
            "pm_concept": "Prioritization frameworks",
            "ai_concept": "Foundation vs fine-tuned models",
            "challenge": "When would you choose fine-tuning over RAG?",
        })
        wrapper, _ = _make_wrapper(good)
        gen = LessonGenerator(wrapper, [_make_node()])
        lesson = gen.generate()
        assert "Prioritization" in lesson.pm_concept
        assert "Foundation" in lesson.ai_concept
        assert "fine-tuning" in lesson.challenge

    def test_lesson_carries_concept_node_metadata(self):
        good = json.dumps({
            "pm_concept": "p", "ai_concept": "a", "challenge": "c"})
        wrapper, _ = _make_wrapper(good)
        node = _make_node("ai-fluency/foundation-vs-finetuned",
                          gap="AI technical fluency",
                          source=[{"url": "https://x.com", "type": "report"}])
        gen = LessonGenerator(wrapper, [node])
        lesson = gen.generate()
        assert lesson.concept_node_id == "ai-fluency/foundation-vs-finetuned"
        assert lesson.concept_gap == "AI technical fluency"
        assert len(lesson.concept_source) > 0

    def test_challenge_type_set_on_lesson(self):
        good = json.dumps({
            "pm_concept": "p", "ai_concept": "a", "challenge": "c"})
        wrapper, _ = _make_wrapper(good)
        gen = LessonGenerator(wrapper, [_make_node()])
        lesson = gen.generate()
        assert lesson.challenge_type == ChallengeType.CONCEPT_RECALL

    def test_uses_haiku_model(self):
        good = json.dumps({
            "pm_concept": "p", "ai_concept": "a", "challenge": "c"})
        wrapper, client = _make_wrapper(good)
        gen = LessonGenerator(wrapper, [_make_node()])
        gen.generate()
        assert client.calls[0][0] == ModelName.HAIKU

    def test_system_prompt_enforces_cold_questions(self):
        good = json.dumps({
            "pm_concept": "p", "ai_concept": "a", "challenge": "c"})
        wrapper, client = _make_wrapper(good)
        gen = LessonGenerator(wrapper, [_make_node()])
        gen.generate()
        system_prompt = client.calls[0][1]
        assert "COLD" in system_prompt or "cold" in system_prompt.lower()
        assert "no hint" in system_prompt.lower()
