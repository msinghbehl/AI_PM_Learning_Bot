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
from ingestion_agent.drafter import Drafter
from ingestion_agent.fetcher import FetchResult, extract_links, fetch_url, read_source
from ingestion_agent.reference import load_reference_framework
from ingestion_agent.schema import ConceptNode
from ingestion_agent.writer import merge_proposals, write_staging_yaml

# Default paths (relative to repo root)
DEFAULT_SOURCES_DIR = "sources"
DEFAULT_REFERENCE_DIR = "sources/reference-framework-inputs"
DEFAULT_OUTPUT = "curriculum/ai-technical-fluency.staging.yaml"


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
        for source in sources:
            print(f"Ingesting: {source}", file=sys.stderr)
            results = _ingest_one(source, drafter, critic, reference_framework)
            all_results.extend(results)
            print(f"  → {len(results)} proposals", file=sys.stderr)

        # Write staging YAML
        write_staging_yaml(all_results, args.output)
        print(
            f"\nWrote {len(all_results)} proposals to {args.output}", file=sys.stderr)

        # Gate 6 final gap pass (spec §5): flag concepts named in ≥2 JDs
        # but not covered by any node
        covered_ids = {node.id for node, _ in all_results}
        covered_keywords = {
            nid.split("/")[-1].replace("-", " ") for nid in covered_ids
        }
        gap_count = 0
        for concept in reference_framework.all_concepts_lower:
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
