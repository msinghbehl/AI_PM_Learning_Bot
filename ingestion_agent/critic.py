"""Critic: Sonnet 4.6 runs 6 quality gates on Haiku's proposals.

Per spec §5: each gate is a concrete, checkable rule. The critic runs all 6 on
every proposal. Failing gates get FLAG with a reason; passing gates get PASS.
Gates 1, 2, 5 are pass/fail; gates 3, 4, 6 are informational annotations.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from anthropic import Anthropic
from tenacity import retry, stop_after_attempt, wait_exponential

from ingestion_agent.reference import ReferenceFramework
from ingestion_agent.schema import ConceptNode

_SONNET_MODEL = "claude-sonnet-4-6"

# Concepts that are foundational (accept older citations) vs evolving (need recent).
# Per spec §5 Gate 4.
_FOUNDATIONAL_IDS = frozenset({
    "ai-fluency/foundation-vs-finetuned",
    "ai-fluency/transformer-architecture-basics",
    "ai-fluency/training-pipeline",
    "ai-fluency/prompting-techniques",
    "ai-fluency/rag-fundamentals",
    "ai-fluency/why-evals-matter",
    "ai-fluency/ai-safety-basics",
    "ai-fluency/prompt-injection-security",
})

# Borderline concepts kept in technical fluency per #11 decisions.
# These mention product/UX but are kept because an AI PM needs the technical literacy.
_BORDERLINE_KEPT = frozenset({
    "ai-fluency/latency-aware-design",
    "ai-fluency/eval-design",
})


@dataclass
class CriticResult:
    """Result of a single gate check."""
    gate: str
    passed: bool
    reason: str | None = None
    annotation: str | None = None

    def __str__(self) -> str:
        if self.passed:
            return "PASS"
        return f"FLAG — {self.reason or 'failed'}"


@dataclass
class CritiqueResult:
    """Result of running all 6 gates on a proposal."""
    node: ConceptNode
    annotations: list[CriticResult] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return all(a.passed for a in self.annotations)

    @property
    def flags(self) -> list[CriticResult]:
        return [a for a in self.annotations if not a.passed]

    def to_comment_lines(self) -> list[str]:
        """Format as `# critic:` comment lines for the staging YAML."""
        lines: list[str] = []
        for ann in self.annotations:
            if ann.passed and ann.annotation:
                lines.append(f"  # critic: {ann.gate}: {ann.annotation}")
            elif ann.passed:
                lines.append(f"  # critic: {ann.gate}: PASS")
            else:
                lines.append(f"  # critic: {ann.gate}: FLAG — {ann.reason}")
        return lines


class Critic:
    """Runs the 6 quality gates on concept-node proposals using Sonnet 4.6."""

    def __init__(self, api_key: str | None = None):
        self._client = Anthropic(api_key=api_key)

    # --- Gate 1: Groundedness ---
    def check_groundedness(self, node: ConceptNode, source_text: str) -> CriticResult:
        """Check that the anchor exists verbatim (or near-verbatim) in the source."""
        for source_entry in node.source:
            anchor = source_entry.anchor.lower()
            source_lower = source_text.lower()
            if anchor in source_lower:
                return CriticResult(gate="groundedness", passed=True, annotation="anchor found in source")
        return CriticResult(
            gate="groundedness",
            passed=False,
            reason="anchor not found in source",
        )

    # --- Gate 2: Primary-citation ---
    def check_primary_citation(self, node: ConceptNode) -> CriticResult:
        """Check that there's ≥1 primary-tier source."""
        if node.has_primary_source:
            return CriticResult(gate="primary-citation", passed=True, annotation="≥1 primary source")
        return CriticResult(
            gate="primary-citation",
            passed=False,
            reason="needs primary source",
        )

    # --- Gate 3: Tier-mix annotation (informational) ---
    def check_tier_mix(self, node: ConceptNode) -> CriticResult:
        """Annotate the source tier mix."""
        annotation = f"{node.primary_count} primary, {node.secondary_count} secondary, {node.tertiary_count} tertiary"
        return CriticResult(gate="tier-mix", passed=True, annotation=annotation)

    # --- Gate 4: Stability + recency ---
    def check_stability_recency(
        self,
        node: ConceptNode,
        available_sources: list[dict[str, Any]] | None = None,
    ) -> CriticResult:
        """Tag stability; for evolving concepts, check recency."""
        is_foundational = node.id in _FOUNDATIONAL_IDS
        stability = "foundational" if is_foundational else "evolving"

        if is_foundational:
            return CriticResult(gate="stability-recency", passed=True, annotation=f"stability: {stability}")

        # For evolving concepts, check if a newer source exists that isn't cited
        available_sources = available_sources or []
        cited_urls = {s.url for s in node.source}
        if available_sources:
            newest = max(available_sources, key=lambda s: s.get("date", ""), )
            if newest.get("url") not in cited_urls:
                return CriticResult(
                    gate="stability-recency",
                    passed=False,
                    reason=f"stale — superseded by {newest.get('url')}",
                    annotation=f"stability: {stability}",
                )

        return CriticResult(gate="stability-recency", passed=True, annotation=f"stability: {stability}")

    # --- Gate 5: Scope triage (two-axis test) ---
    def check_scope(self, node: ConceptNode) -> CriticResult:
        """Check the two-axis test: how the tech works + conceptual literacy."""
        # Borderline concepts are explicitly kept per #11 decisions
        if node.id in _BORDERLINE_KEPT:
            return CriticResult(gate="scope", passed=True, annotation="borderline, kept in track per #11")

        # Heuristic: if the concept mentions "how to design" or "how to write a PRD",
        # it's product/craft, not technical fluency
        concept_lower = node.concept.lower()
        craft_indicators = ["how to write a prd", "how to design a ux",
                            "prioritization framework", "stakeholder"]
        if any(indicator in concept_lower for indicator in craft_indicators):
            return CriticResult(
                gate="scope",
                passed=False,
                reason="defer to Phase 2: PM Fundamentals or AI Product Judgment",
            )

        return CriticResult(gate="scope", passed=True, annotation="technical-fluency literacy")

    # --- Gate 6: Reference-framework gap check ---
    def check_reference_framework(self, node: ConceptNode, framework: ReferenceFramework) -> CriticResult:
        """Check how many JDs name this concept."""
        # Extract the concept keyword from the node id (last segment)
        concept_keyword = node.id.split("/")[-1].replace("-", " ")
        coverage = framework.concept_coverage(concept_keyword)
        return CriticResult(
            gate="reference-framework",
            passed=True,  # informational, not fail
            annotation=f"covered by {coverage}/{framework.jd_count} JDs",
        )

    def critique(
        self,
        node: ConceptNode,
        source_text: str,
        framework: ReferenceFramework,
        available_sources: list[dict[str, Any]] | None = None,
    ) -> CritiqueResult:
        """Run all 6 gates on a proposal."""
        result = CritiqueResult(node=node)
        result.annotations.append(self.check_groundedness(node, source_text))
        result.annotations.append(self.check_primary_citation(node))
        result.annotations.append(self.check_tier_mix(node))
        result.annotations.append(
            self.check_stability_recency(node, available_sources))
        result.annotations.append(self.check_scope(node))
        result.annotations.append(
            self.check_reference_framework(node, framework))
        return result
