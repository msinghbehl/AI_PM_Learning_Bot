"""Curriculum loader — loads the 22-node AI Technical Fluency YAML.

Per #7: the curriculum is grounded, cited, and committed at build time. No
runtime fetcher in Phase 1. Every node carries `gap` and `source` (mission-
grounded). The loader validates the mission-grounded invariant on load.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from coach.config import ChallengeType, Difficulty


@dataclass(frozen=True)
class CurriculumNode:
    """One concept node in the curriculum (PLAN §4.2 schema)."""

    id: str
    gap: str
    concept: str
    difficulty: Difficulty
    source: list[dict[str, str]]
    related_gaps: list[str] = field(default_factory=list)
    prerequisites: list[str] = field(default_factory=list)
    challenge_types: list[ChallengeType] = field(default_factory=list)
    phase: int = 1

    @property
    def is_root(self) -> bool:
        return len(self.prerequisites) == 0

    @property
    def has_gap_and_source(self) -> bool:
        """Mission-grounded invariant: every node traces to a gap + has a source."""
        return bool(self.gap) and len(self.source) > 0


def load_curriculum(path: Path) -> list[CurriculumNode]:
    """Load and validate the curriculum YAML.

    Raises ValueError if any node is missing `gap` or `source` (mission-grounded
    invariant) or has an invalid difficulty/challenge_type.
    """
    raw: list[dict[str, Any]] = yaml.safe_load(path.read_text())
    if not isinstance(raw, list):
        raise ValueError(f"curriculum at {path} must be a list of nodes")

    nodes: list[CurriculumNode] = []
    for i, entry in enumerate(raw):
        node = _parse_node(entry, i, path)
        if not node.has_gap_and_source:
            raise ValueError(
                f"node {node.id!r} violates mission-grounded invariant: "
                f"must have gap and source"
            )
        nodes.append(node)
    return nodes


def _parse_node(entry: dict[str, Any], index: int, path: Path) -> CurriculumNode:
    """Parse one raw YAML entry into a validated CurriculumNode."""
    try:
        difficulty = Difficulty(entry["difficulty"])
    except (KeyError, ValueError) as exc:
        raise ValueError(
            f"node #{index} in {path} has invalid difficulty: {entry.get('difficulty')!r}"
        ) from exc

    challenge_types: list[ChallengeType] = []
    for ct in entry.get("challenge_types", []):
        try:
            challenge_types.append(ChallengeType(ct))
        except ValueError as exc:
            raise ValueError(
                f"node {entry.get('id', index)!r} has invalid challenge_type: {ct!r}"
            ) from exc

    return CurriculumNode(
        id=entry["id"],
        gap=entry.get("gap", ""),
        concept=entry["concept"],
        difficulty=difficulty,
        source=entry.get("source", []),
        related_gaps=entry.get("related_gaps", []),
        prerequisites=entry.get("prerequisites", []),
        challenge_types=challenge_types,
        phase=entry.get("phase", 1),
    )
