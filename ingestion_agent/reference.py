"""Reference framework loader for Gate 6 (completeness gap check).

Loads JDs from sources/reference-framework-inputs/ai_pm_jobs/ and the interview
questions doc. Extracts concept keywords so the critic can check how many JDs
name a given concept, and flag gaps (concepts in JDs but not in the curriculum).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ReferenceFramework:
    """The reference framework: JDs + interview questions, with concept extraction."""
    jd_count: int = 0
    jd_concepts: list[set[str]] = field(default_factory=list)  # one set per JD
    interview_concepts: set[str] = field(default_factory=set)
    all_concepts_lower: set[str] = field(default_factory=set)

    def concept_coverage(self, concept: str) -> int:
        """How many JDs mention this concept (case-insensitive substring match).

        Checks if the concept (lowercased) appears as a substring of any
        indexed phrase in each JD's concept set. This catches both keyword
        matches ("rag" matches "- RAG") and phrase matches ("model routing"
        matches "what is model routing?").
        """
        concept_lower = concept.lower()
        count = 0
        for jd_set in self.jd_concepts:
            if any(concept_lower in phrase for phrase in jd_set):
                count += 1
        return count

    def is_covered(self, concept: str) -> bool:
        """True if the concept appears in any JD or the interview questions.

        Does substring matching against indexed phrases so multi-word concepts
        like "model routing" match the phrase "what is model routing?".
        """
        concept_lower = concept.lower()
        return any(
            concept_lower in phrase
            for phrase in self.all_concepts_lower
        )


def _extract_concepts(text: str) -> set[str]:
    """Extract concept-like keywords from JD/interview text.

    Two levels of indexing:
    1. Whole bullet/heading phrases (for semantic context the critic can read).
    2. Individual keywords (lowercased, alphanumeric, 3+ chars) so substring
       matching works: a JD mentioning "RAG" indexes "rag", so
       concept_coverage("rag") counts it.

    This is intentionally coarse — the critic (Sonnet) does semantic matching;
    this just gives it a searchable keyword index.
    """
    concepts: set[str] = set()
    lower = text.lower()

    # Extract bullet point content (lines starting with -)
    for match in re.finditer(r"^\s*-\s*(.+)$", lower, re.MULTILINE):
        phrase = match.group(1).strip().rstrip(".")
        if 2 < len(phrase) < 100:  # >= 3 chars
            concepts.add(phrase)
            # Also index individual words for keyword matching
            for word in re.findall(r"[a-z0-9]+", phrase):
                if len(word) >= 3:
                    concepts.add(word)

    # Extract heading content (lines starting with #)
    for match in re.finditer(r"^#+\s*(.+)$", lower, re.MULTILINE):
        phrase = match.group(1).strip()
        if 2 < len(phrase) < 100:  # >= 3 chars
            concepts.add(phrase)
            for word in re.findall(r"[a-z0-9]+", phrase):
                if len(word) >= 3:
                    concepts.add(word)

    # Note: we do NOT index every word from the full body — that would add
    # every common English word ("the", "and", "for") and make is_covered()
    # return True for anything. Only bullet/heading phrases + their keywords
    # are indexed, which gives enough coverage signal for the critic.

    return concepts


def load_reference_framework(ref_dir: Path | str) -> ReferenceFramework:
    """Load JDs and interview questions from the reference-framework-inputs dir.

    Expected structure:
      ref_dir/ai_pm_jobs/*.md  — JD files
      ref_dir/ai-pm-interview-guidance.md — interview questions
    """
    ref_dir = Path(ref_dir)
    framework = ReferenceFramework()

    if not ref_dir.exists():
        return framework

    # Load JDs
    jd_dir = ref_dir / "ai_pm_jobs"
    if jd_dir.exists():
        for jd_file in sorted(jd_dir.glob("*.md")):
            text = jd_file.read_text(encoding="utf-8")
            concepts = _extract_concepts(text)
            framework.jd_concepts.append(concepts)
            framework.all_concepts_lower.update(concepts)
        framework.jd_count = len(framework.jd_concepts)

    # Load interview questions
    interview_file = ref_dir / "ai-pm-interview-guidance.md"
    if interview_file.exists():
        text = interview_file.read_text(encoding="utf-8")
        concepts = _extract_concepts(text)
        framework.interview_concepts = concepts
        framework.all_concepts_lower.update(concepts)

    return framework
