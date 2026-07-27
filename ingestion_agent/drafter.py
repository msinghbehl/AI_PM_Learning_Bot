"""Drafter: Haiku draft call that produces concept-node proposals from a source.

Per spec §6: takes fetched source content + the 21-node target list, produces
YAML proposals for any nodes the source grounds. Uses Haiku 4.5.
"""
from __future__ import annotations

import re
from typing import Any

import yaml
from anthropic import Anthropic
from tenacity import retry, stop_after_attempt, wait_exponential

from ingestion_agent.schema import ConceptNode

# The 21 target concept nodes (spec §4).
TARGET_NODES: list[dict[str, Any]] = [
    {"id": "ai-fluency/foundation-vs-finetuned",
        "concept": "Pretrained foundation models vs task-specific fine-tuned models", "prerequisites": []},
    {"id": "ai-fluency/transformer-architecture-basics", "concept": "Transformers, attention, tokens",
        "prerequisites": ["ai-fluency/foundation-vs-finetuned"]},
    {"id": "ai-fluency/training-pipeline", "concept": "Pretraining → SFT → RLHF/DPO",
        "prerequisites": ["ai-fluency/transformer-architecture-basics"]},
    {"id": "ai-fluency/reading-model-reports", "concept": "How to read a GPT-4/Claude/Gemini report",
        "prerequisites": ["ai-fluency/training-pipeline"]},
    {"id": "ai-fluency/context-windows", "concept": "What a context window is, why it grew",
        "prerequisites": ["ai-fluency/foundation-vs-finetuned"]},
    {"id": "ai-fluency/long-context-vs-rag", "concept": "When long-context makes RAG unnecessary vs when RAG wins",
        "prerequisites": ["ai-fluency/context-windows", "ai-fluency/rag-fundamentals"]},
    {"id": "ai-fluency/prompting-techniques", "concept": "CoT, few-shot, system prompts, structured outputs",
        "prerequisites": ["ai-fluency/foundation-vs-finetuned"]},
    {"id": "ai-fluency/rag-fundamentals", "concept": "RAG — retrieve chunks, stuff context, generate",
        "prerequisites": ["ai-fluency/prompting-techniques"]},
    {"id": "ai-fluency/fine-tuning-when-why", "concept": "When to fine-tune vs prompt vs RAG",
        "prerequisites": ["ai-fluency/rag-fundamentals", "ai-fluency/training-pipeline"]},
    {"id": "ai-fluency/llm-wiki-knowledge-compounding", "concept": "Karpathy LLM-Wiki pattern — compile once vs retrieve per query",
        "prerequisites": ["ai-fluency/rag-fundamentals"]},
    {"id": "ai-fluency/why-evals-matter", "concept": "Goodhart's law, MMLU/HumanEval, custom evals",
        "prerequisites": ["ai-fluency/foundation-vs-finetuned"]},
    {"id": "ai-fluency/eval-design", "concept": "Custom evals — golden sets, rubric grading, regression suites",
        "prerequisites": ["ai-fluency/why-evals-matter"]},
    {"id": "ai-fluency/llm-as-judge", "concept": "LLMs grading LLMs — same-model trap, position bias",
        "prerequisites": ["ai-fluency/eval-design"]},
    {"id": "ai-fluency/human-eval-vs-automated", "concept": "When human judgment vs automated evals suffice",
        "prerequisites": ["ai-fluency/llm-as-judge"]},
    {"id": "ai-fluency/inference-cost-economics", "concept": "Cost-per-query, token economics, $/1M-token model",
        "prerequisites": ["ai-fluency/foundation-vs-finetuned"]},
    {"id": "ai-fluency/latency-aware-design", "concept": "TTFT, throughput, streaming — latency shapes UX",
        "prerequisites": ["ai-fluency/inference-cost-economics"]},
    {"id": "ai-fluency/reading-model-cards", "concept": "What to look for in a model card",
        "prerequisites": ["ai-fluency/training-pipeline"]},
    {"id": "ai-fluency/model-routing", "concept": "Cheap/strong tier routing, fallback ladders, cost caps",
        "prerequisites": ["ai-fluency/inference-cost-economics", "ai-fluency/fine-tuning-when-why"]},
    {"id": "ai-fluency/hallucination-causes-mitigations", "concept": "Why LLMs hallucinate + mitigation stack",
        "prerequisites": ["ai-fluency/rag-fundamentals", "ai-fluency/context-windows"]},
    {"id": "ai-fluency/ai-safety-basics", "concept": "Alignment, RLHF, constitutional AI, safety filters",
        "prerequisites": ["ai-fluency/training-pipeline", "ai-fluency/hallucination-causes-mitigations"]},
    {"id": "ai-fluency/prompt-injection-security", "concept": "Adversarial inputs — direct, indirect via RAG/tools, jailbreaks",
        "prerequisites": ["ai-fluency/prompting-techniques", "ai-fluency/rag-fundamentals"]},
]

_HAIKU_MODEL = "claude-haiku-4-5"


def _format_target_nodes_table() -> str:
    """Format the 21 target nodes as a table for the Haiku prompt."""
    lines = ["| id | concept | prerequisites |",
             "|----|---------|---------------|"]
    for node in TARGET_NODES:
        prereqs = ", ".join(node["prerequisites"]
                            ) if node["prerequisites"] else "(root)"
        lines.append(f"| {node['id']} | {node['concept']} | {prereqs} |")
    return "\n".join(lines)


def _build_draft_prompt(source_content: str, source_url: str) -> str:
    """Build the Haiku draft prompt per spec §6."""
    return f"""You are drafting concept nodes for an AI Technical Fluency curriculum.

Source content (fetched):
{source_content[:50000]}

Source URL: {source_url}

Target concept nodes (author proposals for any that this source grounds):
{_format_target_nodes_table()}

For each target node that this source grounds, produce a YAML proposal with all 9 fields:
id, gap, concept, difficulty, source (list with url/type/accessed_at/anchor), related_gaps, prerequisites, challenge_types, phase.

The `anchor` must be a verbatim phrase from the source text.
The `source.url` should be {source_url} (the source you're grounding in).
The `accessed_at` should be today's date.
Only propose nodes the source actually grounds — do not invent concepts.
If the source doesn't ground any node, return an empty list.

Output ONLY the YAML list inside a ```yaml code block."""


def _extract_yaml_block(text: str) -> str:
    """Extract the content of a ```yaml ... ``` code block from LLM output."""
    match = re.search(r"```ya?ml\n(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    # Fallback: if no code block, try parsing the whole text as YAML
    return text.strip()


class Drafter:
    """Drafts concept-node proposals from a source using Haiku 4.5."""

    def __init__(self, api_key: str | None = None):
        self._client = Anthropic(api_key=api_key)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    def draft(self, source_content: str, source_url: str) -> list[ConceptNode]:
        """Draft concept-node proposals from source content.

        Returns a list of ConceptNode proposals. Empty if the source grounds no nodes.
        """
        prompt = _build_draft_prompt(source_content, source_url)

        response = self._client.messages.create(
            model=_HAIKU_MODEL,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )

        text = response.content[0].text if response.content else ""
        yaml_text = _extract_yaml_block(text)

        if not yaml_text:
            return []

        try:
            parsed = yaml.safe_load(yaml_text)
        except yaml.YAMLError:
            return []

        if not parsed or not isinstance(parsed, list):
            return []

        proposals: list[ConceptNode] = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            try:
                node = ConceptNode(**item)
                proposals.append(node)
            except Exception:
                # Skip invalid proposals — the critic would flag them anyway
                continue

        return proposals
