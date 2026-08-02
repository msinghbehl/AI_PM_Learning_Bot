"""Lesson generator — generates one daily lesson via Haiku.

Per #32 Phase 2: loads the curriculum, picks a concept, generates a PM concept
+ AI concept + one rotating challenge via Haiku. Questions are cold — no hint,
no scaffold (desirable difficulty arm a). Every surfaced concept traces to a
gap and source (mission-grounded).

The generator is pure logic over an injected CallLLM — tests inject a fake.
"""
from __future__ import annotations

import itertools
import logging
from dataclasses import dataclass, field
from typing import Any

from coach.call_llm import CallLLM
from coach.config import ChallengeType, ModelName
from coach.curriculum import CurriculumNode

log = logging.getLogger("coach.lesson")

# System prompt for lesson generation — enforces cold questions (arm a).
_SYSTEM = """\
You are Coach, a personalized AI PM learning coach. Generate a daily lesson.

Rules:
- Output ONLY a valid JSON object, no markdown fences.
- The lesson has three parts: pm_concept, ai_concept, and challenge.
- The challenge must be a COLD question — no hint, no scaffold, no reminder \
of prior lessons. The user must retrieve from memory.
- Every concept must trace to a gap in the ideal AI PM profile.
"""


@dataclass(frozen=True)
class Lesson:
    """One daily lesson — PM concept + AI concept + one challenge."""

    pm_concept: str
    ai_concept: str
    challenge: str
    challenge_type: ChallengeType
    concept_node_id: str
    concept_gap: str
    concept_source: list[dict[str, str]]


# Schema for the structured LLM output.
_LESSON_SCHEMA: dict[str, type] = {
    "pm_concept": str,
    "ai_concept": str,
    "challenge": str,
}


class LessonGenerator:
    """Generates daily lessons by rotating challenge types across curriculum nodes."""

    def __init__(self, call_llm: CallLLM, nodes: list[CurriculumNode]) -> None:
        self._call_llm = call_llm
        self._nodes = nodes
        self._challenge_cycle = itertools.cycle([
            ChallengeType.CONCEPT_RECALL,
            ChallengeType.SCENARIO,
            ChallengeType.TECHNICAL_DEEP_DIVE,
        ])
        self._node_cycle = itertools.cycle(nodes)

    def next_challenge_type(self) -> ChallengeType:
        """Return the next challenge type in the rotation (for testing)."""
        return next(self._challenge_cycle)

    def next_node(self) -> CurriculumNode:
        """Return the next curriculum node in the rotation (for testing)."""
        return next(self._node_cycle)

    def generate(self, caps: Any = None) -> Lesson:
        """Generate one daily lesson.

        Picks the next node and challenge type in rotation, then asks Haiku to
        generate the lesson text. The challenge is cold (no hint/scaffold).
        """
        node = self.next_node()
        challenge_type = self.next_challenge_type()

        user_prompt = (
            f"Generate a lesson for this curriculum node:\n"
            f"  id: {node.id}\n"
            f"  concept: {node.concept}\n"
            f"  gap: {node.gap}\n"
            f"  difficulty: {node.difficulty.value}\n"
            f"  challenge_type: {challenge_type.value}\n\n"
            f"Return JSON with keys: pm_concept (str), ai_concept (str), "
            f"challenge (str). The challenge must be a {challenge_type.value} "
            f"question — cold, no hint, no scaffold."
        )

        result = self._call_llm.structured(
            system=_SYSTEM,
            messages=[{"role": "user", "content": user_prompt}],
            schema=_LESSON_SCHEMA,
            model=ModelName.HAIKU,
            purpose="generate",
            caps=caps,
        )

        return Lesson(
            pm_concept=result["pm_concept"],
            ai_concept=result["ai_concept"],
            challenge=result["challenge"],
            challenge_type=challenge_type,
            concept_node_id=node.id,
            concept_gap=node.gap,
            concept_source=node.source,
        )
