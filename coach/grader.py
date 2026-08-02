"""Rubric loader + grader — rubric-anchored Sonnet grading.

Per #6: grading is rubric-anchored (references a rubric id, never free-form).
Rubric shape = shared _base.yaml skeleton (version, challenge_type, max_score,
scale labels) + type-owned criteria. The grader uses Sonnet and returns a
structured (band, score, feedback) result.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from coach.call_llm import CallLLM
from coach.config import ChallengeType, GradeBand, ModelName

log = logging.getLogger("coach.grader")

_GRADE_SCHEMA: dict[str, type] = {
    "band": str,
    "score": int,
    "feedback": str,
}

_SYSTEM = """\
You are a grader for an AI PM learning coach. Grade the user's answer against \
the rubric provided. Output ONLY a valid JSON object with keys: band (one of \
"below", "approaching", "meets", "exceeds"), score (0-3), feedback (str). \
No markdown fences.
"""


@dataclass(frozen=True)
class Rubric:
    """A loaded rubric — shared skeleton + type-owned criteria."""

    version: int
    challenge_type: str
    max_score: int
    scale: list[dict[str, Any]]
    criteria: list[dict[str, Any]]
    rubric_id: str


def load_rubric(challenge_type: ChallengeType, rubrics_dir: Path) -> Rubric:
    """Load the rubric for a challenge type. Falls back to _base if no type file."""
    type_path = rubrics_dir / f"{challenge_type.value}.yaml"
    base_path = rubrics_dir / "_base.yaml"
    rubric_id = challenge_type.value

    base_raw = yaml.safe_load(base_path.read_text())
    if type_path.exists():
        type_raw = yaml.safe_load(type_path.read_text())
        criteria = type_raw.get("criteria", [])
    else:
        criteria = []

    return Rubric(
        version=base_raw["version"],
        challenge_type=challenge_type.value,
        max_score=base_raw["max_score"],
        scale=base_raw["scale"],
        criteria=criteria,
        rubric_id=rubric_id,
    )


@dataclass(frozen=True)
class GradeResult:
    """One graded answer."""

    band: GradeBand
    score: int
    feedback: str
    rubric_id: str
    model: ModelName


class Grader:
    """Rubric-anchored grader using Sonnet."""

    def __init__(self, call_llm: CallLLM, rubrics_dir: Path) -> None:
        self._call_llm = call_llm
        self._rubrics_dir = rubrics_dir

    def grade(
        self,
        challenge_text: str,
        challenge_type: ChallengeType,
        answer_text: str,
        caps: Any = None,
        purpose: str = "grade",
        dispute_reasoning: str | None = None,
    ) -> GradeResult:
        """Grade one answer against the rubric for its challenge type.

        `purpose` distinguishes grader ("grade") from critic ("critic") calls
        so the fallback ladder can protect the critic. `dispute_reasoning` is
        passed as a separate claim to verify, not concatenated into the answer.
        """
        rubric = load_rubric(challenge_type, self._rubrics_dir)

        user_prompt = (
            f"Rubric (id: {rubric.rubric_id}, max_score: {rubric.max_score}):\n"
            f"  Scale: {[s['label'] for s in rubric.scale]}\n"
            f"  Criteria: {[c['description'] for c in rubric.criteria]}\n\n"
            f"Challenge: {challenge_text}\n\n"
            f"User's answer: {answer_text}\n"
        )
        if dispute_reasoning:
            user_prompt += (
                f"\nDispute reasoning (verify this claim against the rubric, "
                f"do not simply accept it):\n{dispute_reasoning}\n"
            )
        user_prompt += "\nGrade against the rubric. Return band, score, feedback."

        result = self._call_llm.structured(
            system=_SYSTEM,
            messages=[{"role": "user", "content": user_prompt}],
            schema=_GRADE_SCHEMA,
            model=ModelName.SONNET,
            purpose=purpose,
            caps=caps,
        )

        try:
            band = GradeBand(result["band"])
        except ValueError as exc:
            raise ValueError(
                f"grader returned invalid band: {result['band']!r}"
            ) from exc

        return GradeResult(
            band=band,
            score=result["score"],
            feedback=result["feedback"],
            rubric_id=rubric.rubric_id,
            model=ModelName.SONNET,
        )
