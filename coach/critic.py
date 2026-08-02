"""Critic — re-grades every answer; ≥1-band disagreement flags + defers.

Per #6: the critic re-grades every answer. On ≥1-band disagreement with the
grader, the grade is flagged + deferred (neither score writes to SR; interval
held). The critic is never silently dropped under cost pressure (the fallback
ladder protects it). The critic uses Sonnet, same as the grader.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from coach.call_llm import CallLLM
from coach.config import ChallengeType, GradeBand, ModelName
from coach.grader import GradeResult, Grader

log = logging.getLogger("coach.critic")


@dataclass(frozen=True)
class CriticResult:
    """The critic's verdict on a grade."""

    critic_grade: GradeResult
    agrees: bool
    band_delta: int


class Critic:
    """Re-grades every answer; flags disagreement for deferral."""

    def __init__(self, grader: Grader) -> None:
        self._grader = grader

    def review(
        self,
        challenge_text: str,
        challenge_type: ChallengeType,
        answer_text: str,
        original_grade: GradeResult,
        caps: Any = None,
    ) -> CriticResult:
        """Re-grade the answer and compare bands with the original grade.

        The critic uses the same rubric-anchored grading path (Sonnet), but with
        purpose="critic" so the fallback ladder never downgrades it.
        """
        critic_grade = self._grader.grade(
            challenge_text=challenge_text,
            challenge_type=challenge_type,
            answer_text=answer_text,
            caps=caps,
            purpose="critic",
        )
        band_delta = abs(_band_to_int(critic_grade.band) -
                         _band_to_int(original_grade.band))
        agrees = band_delta == 0

        return CriticResult(
            critic_grade=critic_grade,
            agrees=agrees,
            band_delta=band_delta,
        )


def _band_to_int(band: GradeBand) -> int:
    """Convert a GradeBand to its ordinal for delta comparison."""
    order = {
        GradeBand.BELOW: 0,
        GradeBand.APPROACHING: 1,
        GradeBand.MEETS: 2,
        GradeBand.EXCEEDS: 3,
    }
    return order[band]
