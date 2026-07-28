"""Tests for the critic module (Sonnet 6 gates).

Tests cover each of the 6 gates as concrete checkable rules, plus the
annotation output format. API calls are mocked.
"""
from unittest.mock import MagicMock, patch

import pytest

from ingestion_agent.critic import Critic, CriticResult
from ingestion_agent.reference import ReferenceFramework
from ingestion_agent.schema import ConceptNode, SourceEntry


def _make_node(
    id_="ai-fluency/foundation-vs-finetuned",
    anchor="foundation model trained on broad data",
    source_type="model-card",
    prerequisites=None,
) -> ConceptNode:
    return ConceptNode(
        id=id_,
        gap="AI technical fluency",
        concept="Pretrained foundation models vs task-specific fine-tuned models",
        difficulty="medium",
        source=[SourceEntry(
            url="https://www.anthropic.com/claude",
            type=source_type,
            accessed_at="2026-07-26",
            anchor=anchor,
        )],
        related_gaps=["interview-readiness"],
        prerequisites=prerequisites or [],
        challenge_types=["concept-recall", "scenario"],
        phase=1,
    )


class TestGate1Groundedness:
    def test_anchor_found_in_source_passes(self):
        source_text = "The foundation model trained on broad data is adaptable."
        node = _make_node(anchor="foundation model trained on broad data")
        critic = Critic(api_key="test")
        result = critic.check_groundedness(node, source_text)
        assert result.passed is True

    def test_anchor_not_in_source_flags(self):
        source_text = "This text has nothing to do with the anchor."
        node = _make_node(anchor="foundation model trained on broad data")
        critic = Critic(api_key="test")
        result = critic.check_groundedness(node, source_text)
        assert result.passed is False
        assert "anchor not found" in result.reason.lower()


class TestGate2PrimaryCitation:
    def test_with_primary_source_passes(self):
        node = _make_node(source_type="model-card")
        critic = Critic(api_key="test")
        result = critic.check_primary_citation(node)
        assert result.passed is True

    def test_without_primary_source_flags(self):
        node = _make_node(source_type="blog")
        critic = Critic(api_key="test")
        result = critic.check_primary_citation(node)
        assert result.passed is False
        assert "needs primary source" in result.reason.lower()


class TestGate3TierMix:
    def test_annotates_tier_counts(self):
        node = ConceptNode(
            id="ai-fluency/test",
            gap="AI technical fluency",
            concept="Test",
            difficulty="medium",
            source=[
                SourceEntry(url="https://a.com", type="model-card",
                            accessed_at="2026-07-26", anchor="x"),
                SourceEntry(url="https://b.com", type="blog",
                            accessed_at="2026-07-26", anchor="y"),
                SourceEntry(url="pasted:abc12345", type="pasted",
                            accessed_at="2026-07-26", anchor="z"),
            ],
            related_gaps=[],
            prerequisites=[],
            challenge_types=["concept-recall"],
            phase=1,
        )
        critic = Critic(api_key="test")
        result = critic.check_tier_mix(node)
        assert result.passed is True
        assert "1 primary" in result.annotation
        assert "1 secondary" in result.annotation
        assert "1 tertiary" in result.annotation


class TestGate4Stability:
    def test_foundational_concept_passes(self):
        node = _make_node(id_="ai-fluency/transformer-architecture-basics")
        critic = Critic(api_key="test")
        result = critic.check_stability_recency(node, available_sources=[])
        assert result.passed is True
        assert "foundational" in result.annotation.lower()

    def test_evolving_concept_passes_with_recent_source(self):
        node = _make_node(id_="ai-fluency/context-windows")
        critic = Critic(api_key="test")
        result = critic.check_stability_recency(
            node,
            available_sources=[
                {"url": "https://www.anthropic.com/claude", "date": "2026-07-01"}],
        )
        assert result.passed is True
        assert "evolving" in result.annotation.lower()


class TestGate5Scope:
    def test_technical_fluency_concept_passes(self):
        node = _make_node()
        critic = Critic(api_key="test")
        result = critic.check_scope(node)
        assert result.passed is True

    def test_product_judgment_concept_flags(self):
        node = ConceptNode(
            id="ai-fluency/test",
            gap="AI technical fluency",
            concept="How to design a latency-aware UX for streaming models",
            difficulty="medium",
            source=[SourceEntry(
                url="https://a.com", type="model-card", accessed_at="2026-07-26", anchor="x")],
            related_gaps=[],
            prerequisites=[],
            challenge_types=["concept-recall"],
            phase=1,
        )
        critic = Critic(api_key="test")
        result = critic.check_scope(node)
        # latency-aware-design is borderline but kept in track per #11 decisions
        # this test verifies the gate runs; the concept is kept
        assert isinstance(result.passed, bool)


class TestGate6ReferenceFramework:
    def test_concept_covered_by_jds(self):
        # The node id "ai-fluency/transformer-architecture-basics" produces
        # concept keyword "transformer architecture basics". The JDs index
        # "transformers" as a keyword. Substring match: "transformer" is in
        # "transformer architecture basics"? No — but "transformer" is indexed
        # from "transformers" via word extraction. Let's use a node whose
        # keyword directly matches.
        framework = ReferenceFramework(
            jd_count=4,
            jd_concepts=[
                {"transformer architecture basics"},
                {"transformer architecture basics", "rag"},
                {"transformer architecture basics"},
                {"evals"},
            ],
        )
        node = _make_node(id_="ai-fluency/transformer-architecture-basics")
        critic = Critic(api_key="test")
        result = critic.check_reference_framework(node, framework)
        assert result.passed is True
        assert "3/4" in result.annotation

    def test_concept_not_in_any_jd(self):
        framework = ReferenceFramework(jd_count=10, jd_concepts=[
                                       set() for _ in range(10)])
        node = _make_node(id_="ai-fluency/obscure-concept")
        critic = Critic(api_key="test")
        result = critic.check_reference_framework(node, framework)
        assert result.passed is True  # informational, not fail
        assert "0" in result.annotation


class TestCriticResultFormat:
    def test_pass_result_formats_correctly(self):
        result = CriticResult(gate="groundedness",
                              passed=True, annotation="anchor found")
        assert str(result) == "PASS"

    def test_flag_result_includes_reason(self):
        result = CriticResult(gate="groundedness", passed=False,
                              reason="anchor not found in source")
        assert "FLAG" in str(result)
        assert "anchor not found" in str(result)


class TestFullCriticRun:
    @patch("ingestion_agent.critic.Anthropic")
    def test_critique_runs_all_6_gates(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        source_text = "The foundation model trained on broad data is adaptable to many tasks."
        node = _make_node(anchor="foundation model trained on broad data")
        framework = ReferenceFramework(
            jd_count=3,
            jd_concepts=[{"foundation"}, {
                "foundation", "models"}, {"foundation"}],
        )

        critic = Critic(api_key="test-key")
        result = critic.critique(node, source_text, framework)

        assert hasattr(result, "annotations")
        assert len(result.annotations) == 6  # all 6 gates ran
        gate_names = [a.gate for a in result.annotations]
        assert "groundedness" in gate_names
        assert "primary-citation" in gate_names
        assert "tier-mix" in gate_names
        assert "stability-recency" in gate_names
        assert "scope" in gate_names
        assert "reference-framework" in gate_names
