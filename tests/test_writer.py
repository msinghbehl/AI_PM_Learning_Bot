"""Tests for the writer module (staging YAML output with critic comments)."""
from pathlib import Path

import yaml

from ingestion_agent.critic import CritiqueResult, CriticResult
from ingestion_agent.schema import ConceptNode, SourceEntry
from ingestion_agent.writer import write_staging_yaml, merge_proposals


def _make_node(id_="ai-fluency/foundation-vs-finetuned") -> ConceptNode:
    return ConceptNode(
        id=id_,
        gap="AI technical fluency",
        concept="Pretrained foundation models vs task-specific fine-tuned models",
        difficulty="medium",
        source=[SourceEntry(
            url="https://www.anthropic.com/claude",
            type="model-card",
            accessed_at="2026-07-26",
            anchor="foundation model trained on broad data",
        )],
        related_gaps=["interview-readiness"],
        prerequisites=[],
        challenge_types=["concept-recall", "scenario"],
        phase=1,
    )


def _make_critique(node: ConceptNode, passed: bool = True) -> CritiqueResult:
    return CritiqueResult(
        node=node,
        annotations=[
            CriticResult(gate="groundedness", passed=passed, annotation="anchor found" if passed else None,
                         reason=None if passed else "anchor not found"),
            CriticResult(gate="primary-citation",
                         passed=True, annotation="1 primary"),
            CriticResult(gate="tier-mix", passed=True,
                         annotation="1 primary, 0 secondary"),
            CriticResult(gate="stability-recency", passed=True,
                         annotation="stability: foundational"),
            CriticResult(gate="scope", passed=True,
                         annotation="technical-fluency literacy"),
            CriticResult(gate="reference-framework", passed=True,
                         annotation="covered by 3/10 JDs"),
        ],
    )


class TestWriteStagingYaml:
    def test_writes_valid_yaml_with_critic_comments(self, tmp_path):
        node = _make_node()
        critique = _make_critique(node)
        output = tmp_path / "staging.yaml"

        write_staging_yaml([(node, critique)], output)

        text = output.read_text()
        # The critic comments should be present
        assert "# critic:" in text
        # The YAML (with critic comments stripped) must be valid and parseable
        lines = [l for l in text.splitlines() if not l.strip().startswith("# critic:")]
        parsed = yaml.safe_load("\n".join(lines))
        assert isinstance(parsed, list)
        assert len(parsed) == 1
        assert parsed[0]["id"] == "ai-fluency/foundation-vs-finetuned"

    def test_anchor_with_embedded_quotes_is_valid_yaml(self, tmp_path):
        """Anchors containing double quotes must not break the YAML output."""
        node = ConceptNode(
            id="ai-fluency/test-node",
            gap="AI technical fluency",
            concept="Test concept",
            difficulty="medium",
            source=[SourceEntry(
                url="https://example.com",
                type="model-card",
                accessed_at="2026-07-26",
                anchor='a similarity search finds the "most relevant" vector chunks',
            )],
            related_gaps=[],
            prerequisites=[],
            challenge_types=["concept-recall"],
            phase=1,
        )
        critique = _make_critique(node)
        output = tmp_path / "staging.yaml"

        write_staging_yaml([(node, critique)], output)

        text = output.read_text()
        # Strip critic comments and verify the YAML is valid
        lines = [l for l in text.splitlines() if not l.strip().startswith("# critic:")]
        parsed = yaml.safe_load("\n".join(lines))
        assert isinstance(parsed, list)
        assert len(parsed) == 1
        assert "most relevant" in parsed[0]["source"][0]["anchor"]

    def test_empty_proposals_writes_empty_file(self, tmp_path):
        output = tmp_path / "staging.yaml"
        write_staging_yaml([], output)
        assert output.exists()
        assert output.read_text().strip() == "[]"

    def test_multiple_nodes_all_written(self, tmp_path):
        node1 = _make_node("ai-fluency/foundation-vs-finetuned")
        node2 = _make_node("ai-fluency/transformer-architecture-basics")
        node2.prerequisites = ["ai-fluency/foundation-vs-finetuned"]
        critiques = [_make_critique(node1), _make_critique(node2)]
        output = tmp_path / "staging.yaml"

        write_staging_yaml(
            [(node1, critiques[0]), (node2, critiques[1])], output)

        text = output.read_text()
        assert "foundation-vs-finetuned" in text
        assert "transformer-architecture-basics" in text

    def test_flagged_node_includes_flag_reason(self, tmp_path):
        node = _make_node()
        critique = _make_critique(node, passed=False)
        output = tmp_path / "staging.yaml"

        write_staging_yaml([(node, critique)], output)

        text = output.read_text()
        assert "FLAG" in text


class TestMergeProposals:
    def test_merges_same_node_from_multiple_sources(self):
        node1 = _make_node()
        node1.source = [SourceEntry(
            url="https://anthropic.com", type="model-card",
            accessed_at="2026-07-26", anchor="anchor 1"
        )]
        node2 = _make_node()
        node2.source = [SourceEntry(
            url="https://openai.com", type="model-card",
            accessed_at="2026-07-26", anchor="anchor 2"
        )]

        merged = merge_proposals([node1, node2])
        assert len(merged) == 1
        assert len(merged[0].source) == 2  # both sources kept

    def test_different_nodes_not_merged(self):
        node1 = _make_node("ai-fluency/foundation-vs-finetuned")
        node2 = _make_node("ai-fluency/transformer-architecture-basics")

        merged = merge_proposals([node1, node2])
        assert len(merged) == 2

    def test_empty_input_returns_empty(self):
        assert merge_proposals([]) == []
