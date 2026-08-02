"""CLI entrypoint for the ingestion agent.

Per spec §2.1:
  python -m ingestion_agent ingest <path-or-url>
  python -m ingestion_agent ingest --all sources/

Per spec §2.1 one-hop: after reading the primary input, extract hyperlinks and
fetch each one (no recursion). Per spec §2.2: write to
curriculum/ai-technical-fluency.staging.yaml.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from ingestion_agent.critic import Critic
from ingestion_agent.drafter import Drafter, TARGET_NODES
from ingestion_agent.fetcher import FetchResult, extract_links, fetch_url, read_source
from ingestion_agent.reference import load_reference_framework
from ingestion_agent.schema import ConceptNode
from ingestion_agent.writer import merge_proposals, write_staging_yaml

# Deterministic prerequisite map from the spec's 21-node table (spec §4).
# Used to overwrite LLM-drafted prerequisites so DAG edges always match the spec.
_SPEC_PREREQUISITES: dict[str, list[str]] = {
    node["id"]: list(node["prerequisites"]) for node in TARGET_NODES
}

# Default paths (relative to repo root)
DEFAULT_SOURCES_DIR = "sources"
DEFAULT_REFERENCE_DIR = "sources/reference-framework-inputs"
DEFAULT_OUTPUT = "curriculum/ai-technical-fluency.staging.yaml"

# Stopwords for Gate 6 gap check (spec §5). These are terms extracted from JDs
# that are NOT AI technical-fluency concepts — either generic JD boilerplate
# or ML tooling/infrastructure. Filtering them prevents false-positive gaps.
_GAP_STOPWORDS = frozenset({
    # --- Generic English stopwords ---
    "the", "and", "for", "with", "from", "are", "was", "were", "been",
    "have", "has", "had", "this", "that", "these", "those", "into",
    "through", "during", "before", "after", "above", "below", "over",
    "under", "again", "further", "then", "once", "here", "there",
    "when", "where", "why", "how", "all", "each", "few", "more",
    "most", "other", "some", "such", "only", "own", "same", "than",
    "too", "very", "can", "will", "just", "should", "now", "also",
    # --- Generic JD boilerplate (roles, process, adjectives) ---
    "able", "ability", "based", "using", "use", "including", "put",
    "know", "work", "strong", "deep", "high", "low", "real", "key",
    "specific", "required", "related", "ensure", "drive", "focus",
    "focusing", "lead", "master", "track", "field", "domain",
    "years", "bachelor", "role", "summary", "responsibilities",
    "qualifications", "skills", "technical", "business", "product",
    "products", "platform", "platforms", "tools", "framework",
    "frameworks", "systems", "system", "software", "hardware",
    "data", "science", "computer", "engineering", "development",
    "deployment", "management", "performance", "optimization",
    "optimize", "pipeline", "pipelines", "cloud", "aws", "gcp",
    "infrastructure", "environment", "teams", "stakeholder",
    "collaborate", "cross", "functional", "internal", "external",
    "commercial", "enterprise", "market", "strategies", "solutions",
    "needs", "requirements", "roadmaps", "lifecycle", "ideation",
    "launch", "deploy", "monitor", "oversee", "define", "translate",
    "bridge", "align", "driven", "powered", "cutting", "breakthroughs",
    "rise", "edge", "federated", "differential", "privacy",
    "compliance", "ethics", "ethical", "safety", "transparency",
    "alignment", "autonomous", "mobility", "robotics", "device",
    "b2b", "saas", "res", "red", "pre", "post", "time",
    "user", "facing", "familiarity", "proficiency", "experience",
    "expertise", "understanding", "knowledge", "learning", "learn",
    "models", "model", "tuning", "fine", "inference", "api", "gpt",
    "agi", "applications", "generative", "compute", "computing",
    "architectures", "ecosystem", "integration", "commercialize",
    "scalable", "agile",
    # --- Generic JD boilerplate added per Issue #19 ---
    "research", "manager", "developer", "healthcare",
    # --- ML tooling/infrastructure (not AI technical-fluency concepts) ---
    "pytorch", "tensorflow", "kubeflow", "spark", "mlflow", "apache",
    "docker", "kubernetes", "azure",
    # --- Partial-match terms that aren't standalone concepts ---
    "reinforcement",  # subsumed by training-pipeline node
    # --- Multi-word JD section headers ---
    "ai-specific requirements", "key responsibilities", "role summary",
})


def _apply_spec_prerequisites(nodes: list[ConceptNode]) -> list[ConceptNode]:
    """Overwrite each node's prerequisites with the spec-mandated values (spec §4).

    The drafter (Haiku) often leaves prerequisites empty or guesses them
    incorrectly. This deterministic post-processing step looks up each
    node's id in the 21-node target table and overwrites prerequisites with
    the exact spec value, ensuring DAG coherence without relying on LLM
    compliance.

    Returns a new list of ConceptNode copies (immutable update).
    """
    fixed: list[ConceptNode] = []
    for node in nodes:
        spec_prereqs = _SPEC_PREREQUISITES.get(node.id)
        if spec_prereqs is not None and node.prerequisites != spec_prereqs:
            # Create a new node with corrected prerequisites (immutable update)
            node = node.model_copy(update={"prerequisites": spec_prereqs})
        fixed.append(node)
    return fixed


def _load_api_key() -> str | None:
    """Load ANTHROPIC_API_KEY from .env or environment."""
    load_dotenv()
    return os.environ.get("ANTHROPIC_API_KEY")


def _ingest_one(
    source: str,
    drafter: Drafter,
    critic: Critic,
    reference_framework,
) -> list[tuple[ConceptNode, object]]:
    """Ingest a single source: fetch → draft → critique.

    Returns list of (node, critique) tuples.
    """
    # 1. Fetch the source
    result = read_source(source)
    if not result.success:
        print(f"  SKIP: {result.error}", file=sys.stderr)
        return []

    source_url = result.url or source
    source_content = result.content

    # 2. One-hop link following (spec §2.1) — log failures, don't silently drop
    one_hop_contents: list[tuple[str, str]] = [(source_url, source_content)]
    links = extract_links(source_content)
    for link in links[:10]:  # cap at 10 one-hop fetches to avoid runaway
        hop_result = fetch_url(link)
        if hop_result.success:
            one_hop_contents.append((link, hop_result.content))
        else:
            print(
                f"  one-hop skip: {link} — {hop_result.error}", file=sys.stderr)

    # 3. Draft proposals from each fetched content
    all_proposals: list[ConceptNode] = []
    for url, content in one_hop_contents:
        proposals = drafter.draft(source_content=content, source_url=url)
        all_proposals.extend(proposals)

    if not all_proposals:
        print(f"  source {source} grounded 0 nodes", file=sys.stderr)
        return []

    # 4. Merge proposals for the same node id
    merged = merge_proposals(all_proposals)

    # 5. Critique each proposal
    results: list[tuple[ConceptNode, object]] = []
    for node in merged:
        # Use the primary source's content for groundedness check
        source_text = source_content
        for src in node.source:
            if src.is_primary:
                # Try to find the content that matches this source
                for url, content in one_hop_contents:
                    if src.url in url or url in src.url:
                        source_text = content
                        break
                break

        critique = critic.critique(node, source_text, reference_framework)
        results.append((node, critique))

    return results


def _find_sources(sources_dir: str) -> list[str]:
    """Find all source files in sources_dir, skipping reference-framework-inputs/."""
    sources: list[str] = []
    for root, dirs, files in os.walk(sources_dir):
        # Skip the reference-framework-inputs directory
        if "reference-framework-inputs" in Path(root).parts:
            continue
        for f in files:
            if f.startswith("."):
                continue
            if f.endswith((".md", ".txt", ".url", ".pdf")):
                sources.append(str(Path(root) / f))
    return sorted(sources)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ingestion_agent",
        description="Ingest sources and produce concept-node proposals for the AI Technical Fluency curriculum.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    ingest = sub.add_parser("ingest", help="Ingest a source or all sources")
    ingest.add_argument(
        "source", help="Path or URL to ingest, or directory with --all")
    ingest.add_argument("--all", action="store_true",
                        help="Ingest all sources in the directory")
    ingest.add_argument("--output", default=DEFAULT_OUTPUT,
                        help="Output staging YAML path")

    args = parser.parse_args(argv)

    api_key = _load_api_key()
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set. Add it to .env", file=sys.stderr)
        return 1

    drafter = Drafter(api_key=api_key)
    critic = Critic(api_key=api_key)
    reference_framework = load_reference_framework(DEFAULT_REFERENCE_DIR)

    print(
        f"Loaded reference framework: {reference_framework.jd_count} JDs", file=sys.stderr)

    if args.command == "ingest":
        if args.all:
            sources = _find_sources(args.source)
            print(
                f"Ingesting {len(sources)} sources from {args.source}", file=sys.stderr)
        else:
            sources = [args.source]

        all_results: list[tuple[ConceptNode, object]] = []
        all_nodes: list[ConceptNode] = []
        for source in sources:
            print(f"Ingesting: {source}", file=sys.stderr)
            results = _ingest_one(source, drafter, critic, reference_framework)
            all_results.extend(results)
            all_nodes.extend(node for node, _ in results)
            print(f"  → {len(results)} proposals", file=sys.stderr)

        # Merge proposals for the same node id across sources (spec §13)
        merged_nodes = merge_proposals(all_nodes)
        # Deterministic prerequisite fix (spec §4): overwrite LLM-drafted
        # prerequisites with the spec-mandated values so DAG edges are correct.
        merged_nodes = _apply_spec_prerequisites(merged_nodes)
        # Re-run critic on merged nodes (sources may have combined)
        merged_results: list[tuple[ConceptNode, object]] = []
        for node in merged_nodes:
            source_text = ""
            for src in node.source:
                if src.is_primary:
                    source_text = src.anchor  # use the anchor as the grounding text
                    break
            if not source_text and node.source:
                source_text = node.source[0].anchor
            critique = critic.critique(node, source_text, reference_framework)
            merged_results.append((node, critique))

        # Write staging YAML
        write_staging_yaml(merged_results, args.output)
        print(
            f"\nWrote {len(merged_results)} merged proposals to {args.output}", file=sys.stderr)

        # Gate 6 final gap pass (spec §5): flag concepts named in ≥2 JDs
        # but not covered by any node. Filter stopwords to reduce noise.
        covered_ids = {node.id for node, _ in merged_results}
        covered_keywords = {
            nid.split("/")[-1].replace("-", " ") for nid in covered_ids
        }
        gap_count = 0
        for concept in reference_framework.all_concepts_lower:
            if len(concept) < 4 or concept in _GAP_STOPWORDS:
                continue
            if reference_framework.concept_coverage(concept) >= 2:
                if not any(
                    concept in kw or kw in concept for kw in covered_keywords
                ):
                    print(
                        f"  GAP: JDs name '{concept}' but no node covers it; "
                        f"add or consciously defer",
                        file=sys.stderr,
                    )
                    gap_count += 1
        if gap_count:
            print(
                f"\n{gap_count} reference-framework gaps flagged above — "
                f"review and resolve",
                file=sys.stderr,
            )

        print(
            f"Review, edit, then: git mv {args.output} "
            f"curriculum/ai-technical-fluency.yaml", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
