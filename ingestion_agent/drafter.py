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

# Valid enum values for normalization
_VALID_DIFFICULTIES = {"easy", "medium", "hard"}
_DIFFICULTY_MAP = {1: "easy", 2: "medium", 3: "hard",
                   "1": "easy", "2": "medium", "3": "hard"}
_VALID_SOURCE_TYPES = {"model-card", "blog",
                       "paper", "docs", "report", "pasted"}
_TYPE_MAP = {
    "pattern-documentation": "docs", "documentation": "docs", "doc": "docs",
    "model_card": "model-card", "modelcard": "model-card", "card": "model-card",
    "article": "blog", "post": "blog", "newsletter": "blog",
    "research": "paper", "arxiv": "paper", "study": "paper",
    "technical-report": "report", "release": "report", "announcement": "report",
    "text": "pasted", "note": "pasted", "local": "pasted",
}
_VALID_CHALLENGE_TYPES = {"concept-recall", "scenario", "technical-deep-dive"}
_CHALLENGE_MAP = {
    "explain-limitation": "concept-recall", "explain": "concept-recall",
    "compare-approaches": "scenario", "compare": "scenario", "apply": "scenario",
    "deep-dive": "technical-deep-dive", "deepdive": "technical-deep-dive",
    "analysis": "technical-deep-dive", "analyze": "technical-deep-dive",
}
_TARGET_IDS = {n["id"] for n in TARGET_NODES}


def _today() -> str:
    from datetime import date
    return date.today().isoformat()


def _normalize_proposal(item: dict) -> dict:
    """Normalize Haiku's free-form output to match the schema's strict enums.

    Haiku often returns difficulty as a number, type as a free-form string,
    phase as a string, etc. This maps common deviations to valid values.
    """
    # gap: always "AI technical fluency"
    item["gap"] = "AI technical fluency"

    # difficulty: map numbers and invalid strings to valid enum
    diff = item.get("difficulty")
    if diff in _DIFFICULTY_MAP:
        item["difficulty"] = _DIFFICULTY_MAP[diff]
    elif diff not in _VALID_DIFFICULTIES:
        item["difficulty"] = "medium"  # safe default

    # phase: ensure integer 1
    phase = item.get("phase", 1)
    if phase in (2, "2", "phase 2", "parked"):
        item["phase"] = 2
    else:
        item["phase"] = 1

    # source entries: normalize type
    for src in item.get("source", []):
        if isinstance(src, dict):
            stype = src.get("type", "docs")
            if stype not in _VALID_SOURCE_TYPES:
                src["type"] = _TYPE_MAP.get(stype, "docs")
            # accessed_at: ensure string
            if not isinstance(src.get("accessed_at"), str):
                src["accessed_at"] = _today()

    # challenge_types: map to valid values
    cts = item.get("challenge_types", [])
    normalized_cts = []
    for ct in cts:
        if ct in _VALID_CHALLENGE_TYPES:
            normalized_cts.append(ct)
        elif ct in _CHALLENGE_MAP:
            normalized_cts.append(_CHALLENGE_MAP[ct])
    if not normalized_cts:
        normalized_cts = ["concept-recall"]
    item["challenge_types"] = normalized_cts

    # id: skip if not a valid target id
    if item.get("id") not in _TARGET_IDS:
        return None

    # prerequisites: ensure they're valid target ids
    prereqs = item.get("prerequisites", [])
    item["prerequisites"] = [p for p in prereqs if p in _TARGET_IDS]

    return item


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

For each target node that this source grounds, produce a YAML proposal with EXACTLY these 9 fields and values:

- id: (use the exact id from the table above, e.g. "ai-fluency/rag-fundamentals")
- gap: "AI technical fluency"  (always this exact string)
- concept: (one-line description of the concept)
- difficulty: (one of: "easy", "medium", "hard" — as a string, not a number)
- source: (a list with one or more entries, each having:)
    - url: "{source_url}"
    - type: (one of: "model-card", "blog", "paper", "docs", "report", "pasted")
    - accessed_at: "{_today()}"
    - anchor: (a verbatim phrase from the source text, in quotes)
- related_gaps: (list of strings, e.g. ["interview-readiness"], or [])
- prerequisites: (use the exact prerequisite ids from the table above, or [] for root)
- challenge_types: (list of one or more of: "concept-recall", "scenario", "technical-deep-dive")
- phase: 1  (the integer 1, not a string)

CRITICAL RULES:
- The `anchor` MUST be a verbatim phrase copied from the source text above.
- The `id` MUST be one of the exact ids from the table — do not invent new ids.
- The `difficulty` MUST be the string "easy", "medium", or "hard" — not a number.
- The `type` MUST be one of the 6 allowed values — not a free-form string.
- The `phase` MUST be the integer 1.
- Only propose nodes the source actually grounds — do not invent concepts.
- If the source doesn't ground any node, return an empty list.

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
            # Normalize Haiku's free-form output to match schema enums
            item = _normalize_proposal(item)
            if item is None:
                continue
            try:
                node = ConceptNode(**item)
                proposals.append(node)
            except Exception as e:
                # Log the validation error so it's not silently swallowed
                import sys
                print(
                    f"  skipping invalid proposal (id={item.get('id', '?')}): {e}", file=sys.stderr)
                continue

        return proposals
