"""Tests for the reference framework loader (Gate 6 input)."""
from pathlib import Path

from ingestion_agent.reference import ReferenceFramework, load_reference_framework


def _write_jd(tmp_path: Path, company: str, content: str) -> Path:
    jd_dir = tmp_path / "ai_pm_jobs"
    jd_dir.mkdir(exist_ok=True)
    f = jd_dir / f"{company}_AI_PM_JD.md"
    f.write_text(content)
    return f


class TestLoadReferenceFramework:
    def test_loads_jds_and_interview_questions(self, tmp_path):
        ref_dir = tmp_path / "reference-framework-inputs"
        ref_dir.mkdir()
        _write_jd(ref_dir, "Meta",
                  "# Meta AI PM\n- Transformers\n- RAG\n- Evals\n")
        _write_jd(ref_dir, "OpenAI",
                  "# OpenAI AI PM\n- Fine-tuning\n- Safety\n- Evals\n")
        (ref_dir / "ai-pm-interview-guidance.md").write_text(
            "# Interview Qs\n## Category 1\n- Explain how Transformers Work?\n"
        )

        framework = load_reference_framework(ref_dir)

        assert isinstance(framework, ReferenceFramework)
        assert framework.jd_count == 2
        assert "transformers" in framework.all_concepts_lower
        assert "rag" in framework.all_concepts_lower
        assert "evals" in framework.all_concepts_lower
        assert "fine-tuning" in framework.all_concepts_lower

    def test_concept_coverage_counts_how_many_jds_mention(self, tmp_path):
        ref_dir = tmp_path / "reference-framework-inputs"
        ref_dir.mkdir()
        _write_jd(ref_dir, "Meta", "# Meta\n- Transformers\n- RAG\n")
        _write_jd(ref_dir, "OpenAI", "# OpenAI\n- Transformers\n- Evals\n")
        _write_jd(ref_dir, "Anthropic",
                  "# Anthropic\n- Transformers\n- Safety\n")

        framework = load_reference_framework(ref_dir)

        # "transformers" appears in all 3 JDs
        assert framework.concept_coverage("transformers") == 3
        # "rag" appears in 1 JD
        assert framework.concept_coverage("rag") == 1
        # "nonexistent" appears in 0
        assert framework.concept_coverage("nonexistent") == 0

    def test_handles_missing_directory(self, tmp_path):
        framework = load_reference_framework(tmp_path / "nonexistent")
        assert framework.jd_count == 0
        assert framework.all_concepts_lower == set()

    def test_interview_questions_loaded(self, tmp_path):
        ref_dir = tmp_path / "reference-framework-inputs"
        ref_dir.mkdir()
        _write_jd(ref_dir, "Meta", "# Meta\n- Transformers\n")
        (ref_dir / "ai-pm-interview-guidance.md").write_text(
            "# Interview Qs\n- Explain how Transformers Work?\n- What is model routing?\n"
        )

        framework = load_reference_framework(ref_dir)
        # "model routing" appears as a phrase in the interview questions;
        # is_covered checks both JDs and interview questions
        assert framework.is_covered("model routing")
        assert framework.is_covered("transformers")
