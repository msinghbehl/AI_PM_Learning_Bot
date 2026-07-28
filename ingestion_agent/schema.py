"""Pydantic models for the concept-node schema (9 fields) and source entries.

Per spec §3: the concept-node schema has 9 fields (id, gap, concept, difficulty,
source, related_gaps, prerequisites, challenge_types, phase). Each source entry
has 4 fields (url, type, accessed_at, anchor).
"""
from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator


# Tier classification per spec §5 Gate 2: primary types can be sole citation;
# secondary/tertiary can supplement but not be sole citation.
PRIMARY_TYPES = frozenset({"model-card", "paper", "docs", "report"})
SECONDARY_TYPES = frozenset({"blog"})
TERTIARY_TYPES = frozenset({"pasted"})
ALL_SOURCE_TYPES = PRIMARY_TYPES | SECONDARY_TYPES | TERTIARY_TYPES


class SourceEntry(BaseModel):
    """A single cited source for a concept node (spec §3.1)."""

    url: str = Field(...,
                     description="Primary source URL, or pasted:<sha8> for pasted text")
    type: Literal["model-card", "blog", "paper", "docs", "report", "pasted"]
    accessed_at: date = Field(...,
                              description="ISO date the source was accessed")
    anchor: str = Field(..., min_length=1,
                        description="Verbatim phrase from the source grounding the concept")

    @property
    def is_primary(self) -> bool:
        """True if this source is primary-tier (can be a sole citation per Gate 2)."""
        return self.type in PRIMARY_TYPES

    @property
    def is_secondary(self) -> bool:
        return self.type in SECONDARY_TYPES

    @property
    def is_tertiary(self) -> bool:
        return self.type in TERTIARY_TYPES


class ConceptNode(BaseModel):
    """A concept node in the curriculum (spec §3, 9 fields)."""

    id: str = Field(..., description="Namespaced id, e.g. ai-fluency/foundation-vs-finetuned")
    gap: str = Field(...,
                     description="Track name, e.g. 'AI technical fluency'")
    concept: str = Field(..., min_length=1,
                         description="One-line description of the concept")
    difficulty: Literal["easy", "medium", "hard"]
    source: list[SourceEntry] = Field(..., min_length=1,
                                      description="≥1 source entry; must include ≥1 primary")
    related_gaps: list[str] = Field(
        default_factory=list, description="Cross-track links; can be empty")
    prerequisites: list[str] = Field(
        default_factory=list, description="Node ids forming the DAG; empty for root")
    challenge_types: list[Literal["concept-recall",
                                  "scenario", "technical-deep-dive"]]
    phase: Literal[1, 2] = Field(
        1, description="1 = active in SR loop; 2 = authored, parked")
    provenance: list[dict[str, str]] | None = Field(
        default=None,
        description="Optional: tertiary source that pointed at the primary (spec §2.4)",
    )

    @property
    def is_root(self) -> bool:
        """True if this node has no prerequisites (the DAG root)."""
        return len(self.prerequisites) == 0

    @property
    def has_primary_source(self) -> bool:
        """True if at least one source entry is primary-tier (Gate 2 check)."""
        return any(s.is_primary for s in self.source)

    @property
    def primary_count(self) -> int:
        return sum(1 for s in self.source if s.is_primary)

    @property
    def secondary_count(self) -> int:
        return sum(1 for s in self.source if s.is_secondary)

    @property
    def tertiary_count(self) -> int:
        return sum(1 for s in self.source if s.is_tertiary)
