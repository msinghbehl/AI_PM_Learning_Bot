"""Tests for the drafter module (Haiku draft call).

Tests mock the Anthropic API and verify prompt construction + YAML parsing.
"""
from unittest.mock import MagicMock, patch

import pytest

from ingestion_agent.drafter import Drafter, TARGET_NODES
from ingestion_agent.schema import ConceptNode, SourceEntry


SAMPLE_YAML_OUTPUT = """```yaml
- id: ai-fluency/foundation-vs-finetuned
  gap: AI technical fluency
  concept: "Pretrained foundation models vs task-specific fine-tuned models"
  difficulty: medium
  source:
    - url: https://www.anthropic.com/claude
      type: model-card
      accessed_at: 2026-07-26
      anchor: "foundation model trained on broad data"
  related_gaps: [interview-readiness]
  prerequisites: []
  challenge_types: [concept-recall, scenario]
  phase: 1
```"""


class TestTargetNodes:
    def test_has_21_nodes(self):
        assert len(TARGET_NODES) == 21

    def test_root_node_has_no_prerequisites(self):
        root = next(
            n for n in TARGET_NODES if n["id"] == "ai-fluency/foundation-vs-finetuned")
        assert root["prerequisites"] == []

    def test_prompt_injection_node_present(self):
        ids = [n["id"] for n in TARGET_NODES]
        assert "ai-fluency/prompt-injection-security" in ids

    def test_llm_wiki_node_present(self):
        ids = [n["id"] for n in TARGET_NODES]
        assert "ai-fluency/llm-wiki-knowledge-compounding" in ids


class TestDrafter:
    @patch("ingestion_agent.drafter.Anthropic")
    def test_drafts_proposals_from_source(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=SAMPLE_YAML_OUTPUT)]
        mock_client.messages.create.return_value = mock_response

        drafter = Drafter(api_key="test-key")
        proposals = drafter.draft(
            source_content="Some source text about foundation models.",
            source_url="https://www.anthropic.com/claude",
        )

        assert len(proposals) == 1
        assert proposals[0].id == "ai-fluency/foundation-vs-finetuned"
        assert proposals[0].has_primary_source is True

    @patch("ingestion_agent.drafter.Anthropic")
    def test_empty_source_returns_empty_list(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="```yaml\n```")]
        mock_client.messages.create.return_value = mock_response

        drafter = Drafter(api_key="test-key")
        proposals = drafter.draft(
            source_content="Irrelevant content that grounds no nodes.",
            source_url="https://example.com",
        )

        assert proposals == []

    @patch("ingestion_agent.drafter.Anthropic")
    def test_uses_haiku_model(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="```yaml\n```")]
        mock_client.messages.create.return_value = mock_response

        drafter = Drafter(api_key="test-key")
        drafter.draft(source_content="text", source_url="https://example.com")

        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert call_kwargs["model"] == "claude-haiku-4-5"

    @patch("ingestion_agent.drafter.Anthropic")
    def test_invalid_yaml_skipped_gracefully(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(text="```yaml\nnot: valid: yaml: at: all\n```")]
        mock_client.messages.create.return_value = mock_response

        drafter = Drafter(api_key="test-key")
        proposals = drafter.draft(
            source_content="text", source_url="https://example.com"
        )
        assert proposals == []
