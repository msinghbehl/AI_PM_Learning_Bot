"""Tests for the CLI module's prerequisite post-processing (Issue #17) and
gap-check stopword filtering (Issue #19).

Tests verify:
- _apply_spec_prerequisites overwrites LLM-drafted prerequisites with spec values
- _GAP_STOPWORDS filters out generic JD boilerplate and ML tooling terms
"""
from ingestion_agent.cli import _apply_spec_prerequisites, _GAP_STOPWORDS
from ingestion_agent.schema import ConceptNode, SourceEntry


def _make_node(
    node_id: str,
    prerequisites: list[str] | None = None,
) -> ConceptNode:
    """Helper: build a minimal valid ConceptNode for testing."""
    return ConceptNode(
        id=node_id,
        gap="AI technical fluency",
        concept="Test concept",
        difficulty="medium",
        source=[
            SourceEntry(
                url="https://example.com/source",
                type="blog",
                accessed_at="2026-08-01",
                anchor="some verbatim anchor text",
            )
        ],
        related_gaps=[],
        prerequisites=prerequisites if prerequisites is not None else [],
        challenge_types=["concept-recall"],
        phase=1,
    )


class TestApplySpecPrerequisites:
    def test_overwrites_empty_prerequisites(self):
        """Nodes with empty prereqs should get spec-mandated parents."""
        # context-windows should have [foundation-vs-finetuned] per spec
        node = _make_node("ai-fluency/context-windows", prerequisites=[])
        result = _apply_spec_prerequisites([node])
        assert result[0].prerequisites == [
            "ai-fluency/foundation-vs-finetuned"]

    def test_overwrites_incorrect_prerequisites(self):
        """human-eval-vs-automated should point to llm-as-judge, not eval-design."""
        node = _make_node(
            "ai-fluency/human-eval-vs-automated",
            prerequisites=["ai-fluency/eval-design"],  # wrong per spec
        )
        result = _apply_spec_prerequisites([node])
        assert result[0].prerequisites == ["ai-fluency/llm-as-judge"]

    def test_root_node_keeps_empty_prerequisites(self):
        """The root node (foundation-vs-finetuned) should have empty prereqs."""
        node = _make_node(
            "ai-fluency/foundation-vs-finetuned", prerequisites=[])
        result = _apply_spec_prerequisites([node])
        assert result[0].prerequisites == []

    def test_correct_prerequisites_unchanged(self):
        """Nodes with already-correct prereqs should not be modified."""
        node = _make_node(
            "ai-fluency/rag-fundamentals",
            prerequisites=["ai-fluency/prompting-techniques"],
        )
        result = _apply_spec_prerequisites([node])
        assert result[0].prerequisites == ["ai-fluency/prompting-techniques"]

    def test_multiple_nodes_fixed(self):
        """All 7 nodes from the bug report should be fixed correctly."""
        nodes = [
            _make_node("ai-fluency/context-windows", prerequisites=[]),
            _make_node("ai-fluency/rag-fundamentals", prerequisites=[]),
            _make_node("ai-fluency/why-evals-matter", prerequisites=[]),
            _make_node("ai-fluency/inference-cost-economics",
                       prerequisites=[]),
            _make_node("ai-fluency/ai-safety-basics", prerequisites=[]),
            _make_node("ai-fluency/training-pipeline", prerequisites=[]),
            _make_node("ai-fluency/prompting-techniques", prerequisites=[]),
        ]
        result = _apply_spec_prerequisites(nodes)
        assert result[0].prerequisites == [
            "ai-fluency/foundation-vs-finetuned"]
        assert result[1].prerequisites == ["ai-fluency/prompting-techniques"]
        assert result[2].prerequisites == [
            "ai-fluency/foundation-vs-finetuned"]
        assert result[3].prerequisites == [
            "ai-fluency/foundation-vs-finetuned"]
        assert result[4].prerequisites == [
            "ai-fluency/training-pipeline",
            "ai-fluency/hallucination-causes-mitigations",
        ]
        assert result[5].prerequisites == [
            "ai-fluency/transformer-architecture-basics"]
        assert result[6].prerequisites == [
            "ai-fluency/foundation-vs-finetuned"]

    def test_returns_new_objects(self):
        """The function should not mutate the input nodes (immutability)."""
        node = _make_node("ai-fluency/context-windows", prerequisites=[])
        original_prereqs = list(node.prerequisites)
        _apply_spec_prerequisites([node])
        # Original node should be unchanged
        assert node.prerequisites == original_prereqs

    def test_unknown_node_id_unchanged(self):
        """Nodes with ids not in the spec table should be left as-is."""
        # This shouldn't happen in practice (drafter filters to target ids),
        # but the function should handle it gracefully.
        node = _make_node("ai-fluency/nonexistent-node", prerequisites=[])
        result = _apply_spec_prerequisites([node])
        assert result[0].prerequisites == []

    def test_multi_parent_node(self):
        """Nodes with multiple parents should get all of them."""
        # long-context-vs-rag has two parents per spec
        node = _make_node(
            "ai-fluency/long-context-vs-rag", prerequisites=[])
        result = _apply_spec_prerequisites([node])
        assert set(result[0].prerequisites) == {
            "ai-fluency/context-windows",
            "ai-fluency/rag-fundamentals",
        }


class TestGapStopwords:
    """Tests for _GAP_STOPWORDS (Issue #19 — false-positive gap filtering)."""

    def test_generic_jd_boilerplate_filtered(self):
        """Generic JD terms should be in the stopword list."""
        for term in ("research", "manager", "developer", "healthcare"):
            assert term in _GAP_STOPWORDS, f"'{term}' should be a stopword"

    def test_ml_tooling_filtered(self):
        """ML tooling/framework names should be in the stopword list."""
        for term in ("pytorch", "tensorflow", "kubeflow", "spark",
                     "mlflow", "apache", "docker", "kubernetes", "azure"):
            assert term in _GAP_STOPWORDS, f"'{term}' should be a stopword"

    def test_reinforcement_filtered(self):
        """'reinforcement' is subsumed by training-pipeline; should be filtered."""
        assert "reinforcement" in _GAP_STOPWORDS

    def test_real_concepts_not_filtered(self):
        """Genuine AI technical-fluency concepts should NOT be stopwords."""
        # These are concept keywords that should pass through the gap check
        for term in ("rag", "agents", "prompting", "hallucination",
                     "evals", "transformer", "attention", "context",
                     "routing", "fine-tuning"):
            assert term not in _GAP_STOPWORDS, (
                f"'{term}' should NOT be a stopword — it's a real concept")

    def test_all_issue_false_positives_filtered(self):
        """All 12 false positives from the issue should be filtered."""
        false_positives = [
            "research", "required skills", "kubeflow", "apache",
            "pytorch", "manager", "healthcare", "developer",
            "reinforcement", "mlflow", "spark", "tensorflow",
        ]
        for term in false_positives:
            # "required skills" is a multi-word phrase; check if either
            # "required" or "skills" is in the stopword set (both are)
            if " " in term:
                words = term.split()
                assert all(w in _GAP_STOPWORDS for w in words), (
                    f"'{term}' words should all be stopwords")
            else:
                assert term in _GAP_STOPWORDS, (
                    f"'{term}' should be a stopword")
