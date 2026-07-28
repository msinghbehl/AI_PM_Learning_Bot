"""Tests for the concept-node schema (pydantic models)."""
import pytest
from pydantic import ValidationError

from ingestion_agent.schema import SourceEntry, ConceptNode


class TestSourceEntry:
    def test_valid_primary_source(self):
        entry = SourceEntry(
            url="https://www.anthropic.com/claude",
            type="model-card",
            accessed_at="2026-07-26",
            anchor="foundation model trained on broad data",
        )
        assert entry.url == "https://www.anthropic.com/claude"
        assert entry.is_primary is True

    def test_valid_secondary_source(self):
        entry = SourceEntry(
            url="https://example.com/blog",
            type="blog",
            accessed_at="2026-07-26",
            anchor="some quoted phrase",
        )
        assert entry.is_primary is False

    def test_pasted_source_uses_sha8_id(self):
        entry = SourceEntry(
            url="pasted:abc12345",
            type="pasted",
            accessed_at="2026-07-26",
            anchor="quoted text",
        )
        assert entry.is_primary is False
        assert entry.url.startswith("pasted:")

    def test_invalid_type_rejected(self):
        with pytest.raises(ValidationError):
            SourceEntry(
                url="https://example.com",
                type="invalid-type",
                accessed_at="2026-07-26",
                anchor="text",
            )

    def test_invalid_date_rejected(self):
        with pytest.raises(ValidationError):
            SourceEntry(
                url="https://example.com",
                type="blog",
                accessed_at="not-a-date",
                anchor="text",
            )

    def test_empty_anchor_rejected(self):
        with pytest.raises(ValidationError):
            SourceEntry(
                url="https://example.com",
                type="blog",
                accessed_at="2026-07-26",
                anchor="",
            )


class TestConceptNode:
    def _make_source(self, type_="model-card"):
        return SourceEntry(
            url="https://www.anthropic.com/claude",
            type=type_,
            accessed_at="2026-07-26",
            anchor="foundation model trained on broad data",
        )

    def test_valid_root_node(self):
        node = ConceptNode(
            id="ai-fluency/foundation-vs-finetuned",
            gap="AI technical fluency",
            concept="Pretrained foundation models vs task-specific fine-tuned models",
            difficulty="medium",
            source=[self._make_source()],
            related_gaps=["interview-readiness"],
            prerequisites=[],
            challenge_types=["concept-recall", "scenario"],
            phase=1,
        )
        assert node.id == "ai-fluency/foundation-vs-finetuned"
        assert node.is_root is True
        assert node.has_primary_source is True

    def test_node_with_prerequisites_is_not_root(self):
        node = ConceptNode(
            id="ai-fluency/transformer-architecture-basics",
            gap="AI technical fluency",
            concept="Transformers, attention, tokens",
            difficulty="medium",
            source=[self._make_source()],
            related_gaps=[],
            prerequisites=["ai-fluency/foundation-vs-finetuned"],
            challenge_types=["concept-recall"],
            phase=1,
        )
        assert node.is_root is False

    def test_node_without_primary_source_flagged(self):
        node = ConceptNode(
            id="ai-fluency/test-node",
            gap="AI technical fluency",
            concept="Test concept",
            difficulty="easy",
            source=[SourceEntry(
                url="https://example.com/blog",
                type="blog",
                accessed_at="2026-07-26",
                anchor="text",
            )],
            related_gaps=[],
            prerequisites=["ai-fluency/foundation-vs-finetuned"],
            challenge_types=["concept-recall"],
            phase=1,
        )
        assert node.has_primary_source is False

    def test_invalid_difficulty_rejected(self):
        with pytest.raises(ValidationError):
            ConceptNode(
                id="ai-fluency/test",
                gap="AI technical fluency",
                concept="Test",
                difficulty="invalid",
                source=[self._make_source()],
                related_gaps=[],
                prerequisites=[],
                challenge_types=["concept-recall"],
                phase=1,
            )

    def test_invalid_phase_rejected(self):
        with pytest.raises(ValidationError):
            ConceptNode(
                id="ai-fluency/test",
                gap="AI technical fluency",
                concept="Test",
                difficulty="medium",
                source=[self._make_source()],
                related_gaps=[],
                prerequisites=[],
                challenge_types=["concept-recall"],
                phase=3,
            )

    def test_empty_source_list_rejected(self):
        with pytest.raises(ValidationError):
            ConceptNode(
                id="ai-fluency/test",
                gap="AI technical fluency",
                concept="Test",
                difficulty="medium",
                source=[],
                related_gaps=[],
                prerequisites=[],
                challenge_types=["concept-recall"],
                phase=1,
            )
