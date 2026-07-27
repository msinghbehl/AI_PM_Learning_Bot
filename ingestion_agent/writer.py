"""Writer: produces curriculum/ai-technical-fluency.staging.yaml with critic comments.

Per spec §2.2: single file, YAML list of concept nodes with inline `# critic:`
comments. Per spec §13: multiple sources can ground the same node — merge
proposals, keeping the strongest anchors and best tier mix.
"""
from __future__ import annotations

from pathlib import Path

from ingestion_agent.critic import CritiqueResult
from ingestion_agent.schema import ConceptNode


def merge_proposals(proposals: list[ConceptNode]) -> list[ConceptNode]:
    """Merge proposals for the same node id, combining sources.

    Per spec §13: multiple sources can ground the same node — merge,
    keeping the strongest anchors and best tier mix.
    Per coding-style.md: immutable — build new objects, never mutate inputs.
    """
    merged: dict[str, ConceptNode] = {}
    for node in proposals:
        if node.id in merged:
            existing = merged[node.id]
            # Combine sources immutably (deduplicate by url)
            existing_urls = {s.url for s in existing.source}
            new_sources = list(existing.source)
            for source in node.source:
                if source.url not in existing_urls:
                    new_sources.append(source)
                    existing_urls.add(source.url)
            # Create a new node with merged sources (no mutation)
            merged[node.id] = existing.model_copy(
                update={"source": new_sources})
        else:
            merged[node.id] = node.model_copy()
    return list(merged.values())


def _format_node_with_comments(node: ConceptNode, critique: CritiqueResult) -> str:
    """Format a single node as YAML with inline critic comments."""
    lines: list[str] = []

    # Node fields
    lines.append(f"- id: {node.id}")
    lines.append(f"  gap: {node.gap}")
    lines.append(f'  concept: "{node.concept}"')
    lines.append(f"  difficulty: {node.difficulty}")

    # Source list
    lines.append("  source:")
    for src in node.source:
        lines.append(f"    - url: {src.url}")
        lines.append(f"      type: {src.type}")
        lines.append(f"      accessed_at: {src.accessed_at}")
        lines.append(f'      anchor: "{src.anchor}"')

    # Related gaps
    if node.related_gaps:
        lines.append(f"  related_gaps: [{', '.join(node.related_gaps)}]")
    else:
        lines.append("  related_gaps: []")

    # Prerequisites
    if node.prerequisites:
        lines.append(f"  prerequisites: [{', '.join(node.prerequisites)}]")
    else:
        lines.append("  prerequisites: []")

    # Challenge types
    lines.append(f"  challenge_types: [{', '.join(node.challenge_types)}]")

    # Phase
    lines.append(f"  phase: {node.phase}")

    # Critic comments
    for comment_line in critique.to_comment_lines():
        lines.append(comment_line)

    return "\n".join(lines)


def write_staging_yaml(
    proposals: list[tuple[ConceptNode, CritiqueResult]],
    output_path: Path | str,
) -> None:
    """Write the staging YAML file with concept nodes and critic comments.

    Per spec §2.2: single file, YAML list with inline `# critic:` comments.
    Per spec §12: does NOT auto-commit — only writes the file.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not proposals:
        output_path.write_text("[]\n", encoding="utf-8")
        return

    blocks = [_format_node_with_comments(
        node, critique) for node, critique in proposals]
    content = "\n".join(blocks) + "\n"
    output_path.write_text(content, encoding="utf-8")
