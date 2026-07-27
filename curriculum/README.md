# Curriculum — versioned concept nodes

This directory holds the **curriculum YAML** — the versioned knowledge store the bot's SR loop runs against. It's the "wiki layer" in LLM Wiki terms: LLM-proposed, human-reviewed, committed.

## Files

- **`ai-technical-fluency.staging.yaml`** — the ingestion agent's output. Proposals with inline critic annotations (`# critic: ...`). This is the review artifact — Manmeet edits in place, then `git mv` to the final name when satisfied. Created at authoring time, not yet present.
- **`ai-technical-fluency.yaml`** — the final, committed curriculum. The bot loads this for the daily SR loop. Created when Manmeet promotes the staging file.

## Schema (9 fields per node)

Per #7's decision (8 PLAN §4.2 fields) + #11's `phase` extension:

```yaml
- id: ai-fluency/foundation-vs-finetuned        # unique, namespaced
  gap: AI technical fluency                      # track name
  concept: "Pretrained foundation models vs..."  # one-line description
  difficulty: medium                             # easy | medium | hard
  source:                                        # list (per #7) — ≥1 primary required
    - url: https://anthropic.com/...
      type: model-card                           # model-card | blog | paper | docs | report | pasted
      accessed_at: 2026-07-26
      anchor: "foundation model trained on..."   # short quoted phrase grounding the concept
  related_gaps: [interview-readiness]            # cross-track links
  prerequisites: []                              # list of node ids (forms the DAG)
  challenge_types: [concept-recall, scenario]    # rotates daily
  phase: 1                                       # 1 = active in SR loop now; 2 = authored, parked for Phase 2
```

## The 21 nodes (Phase 1 seed track)

See ticket #11's final concept-list comment for the full spec. All 21 marked `phase: 1` initially; the split to activate 20 + park extras happens after the authoring pass reveals what the corpus supports.

## Review gate

Per #3's decision, nothing auto-commits. The staging file is the review artifact; the final file only exists after Manmeet reads, edits, and promotes it. The repo only contains curriculum Manmeet has actually reviewed.
