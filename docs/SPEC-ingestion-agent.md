# Spec: AI Technical Fluency Ingestion Agent

> **Purpose:** This spec is the handoff artifact for a cheaper model that implements the ingestion agent. Every decision is locked (see ticket #11's decision comments); this spec translates those decisions into precise, checkable rules. The implementer reads this spec + `CREDITS.md` + `curriculum/README.md` and builds the agent. No other context needed.
>
> **Scope:** Build the ingestion agent only. Do NOT build the curriculum YAML — that's the HITL authoring pass Manmeet runs after the agent exists. Do NOT build the bot, SR loop, or grader — those are separate Phase 1 work.

## 1. What the agent does

A Python CLI tool that ingests sources from `sources/` and produces concept-node proposals for the AI Technical Fluency curriculum, staged for human review.

**Flow:**
1. Read a source (pasted text, URL, PDF, or GitHub repo README).
2. Follow one-hop links found inside the source (fetch each, no recursion).
3. Haiku drafts concept-node proposals grounded in the source.
4. Sonnet critic runs 6 quality gates on each proposal.
5. Write surviving proposals to `curriculum/ai-technical-fluency.staging.yaml` with inline critic annotations.
6. Manmeet reviews, edits, `git mv` to `curriculum/ai-technical-fluency.yaml`.

The agent is **build-time authoring tool**, not a runtime component. It runs once (or iteratively as Manmeet feeds more sources) to produce the seed curriculum. It is NOT part of the daily bot loop.

## 2. Interface

### 2.1 Input surface

The agent accepts inputs via CLI:

```bash
python -m ingestion_agent ingest <path-or-url>
python -m ingestion_agent ingest sources/primary/anthropic-claude.url
python -m ingestion_agent ingest https://simonwillison.net/2026/Jul/9/gpt-5-6/
python -m ingestion_agent ingest sources/GenerativeAICourse/lessons/09_RAG.md
python -m ingestion_agent ingest --all sources/   # ingest everything in sources/ (skip reference-framework-inputs/)
```

**Accepted input types:**
- **`.md` / `.txt` files** — read directly.
- **`.url` files** — first line is the URL; fetch with `requests` (no JS, no auth). If 401/403/JS-required, log `"couldn't fetch, paste it"` and skip.
- **`.pdf` files** — extract text with `pypdf`.
- **GitHub repo URLs** — fetch README via `gh api repos/<owner>/<repo>/readme` (returns base64; decode). Do NOT clone.
- **Bare URLs** — fetch with `requests`.

**One-hop link following:** after reading the primary input, extract hyperlinks (markdown links `[text](url)` and bare URLs). Fetch each one with `requests` (no JS, no auth). Do NOT recurse from those fetched pages. If a one-hop link resolves to a `.pdf`, download and extract with `pypdf`. If a one-hop link 401s or needs JS, log and skip. GitHub URLs in one-hop links: fetch README via `gh api`.

### 2.2 Output

Single file: `curriculum/ai-technical-fluency.staging.yaml`

Format: YAML list of concept nodes (schema in §3), with inline critic comments. Example:

```yaml
- id: ai-fluency/foundation-vs-finetuned
  gap: AI technical fluency
  concept: "Pretrained foundation models vs task-specific fine-tuned models — what 'foundation' means, why you don't train from scratch, the build-vs-adapt decision"
  difficulty: medium
  source:
    - url: https://www.anthropic.com/claude
      type: model-card
      accessed_at: 2026-07-26
      anchor: "foundation model trained on broad data, adaptable to many tasks"
  related_gaps: [interview-readiness]
  prerequisites: []
  challenge_types: [concept-recall, scenario]
  phase: 1
  # critic: grounded — 1 primary (anthropic), 0 secondary
  # critic: stability: foundational
  # critic: reference-framework: covered by 4/10 JDs
```

### 2.3 Model routing

Per ticket #5: Anthropic direct SDK (`anthropic` Python package). Two tiers:
- **Haiku 4.5** (`claude-haiku-4-5`) — drafts concept proposals from each source.
- **Sonnet 4.6** (`claude-sonnet-4-6`) — runs the 6 critic gates on Haiku's proposals.

API key from env var `ANTHROPIC_API_KEY` (already in `.env`). Use `tenacity` for retries on transient failures (Task_IQ pattern, per #4).

### 2.4 Provenance

When a concept proposal is grounded in a primary source that a tertiary source (LinkedIn post) pointed at, record the tertiary source in a `provenance` field on the node:

```yaml
  provenance:
    - source: sources/linkedin_resources/ai_pm_skills/aakash-gupta-pm-requirements.md
      note: "Manmeet encountered this concept via Aakash Gupta's LinkedIn post"
```

The `provenance` field is optional and only populated when the agent can trace the path tertiary → primary.

## 3. Concept-node schema (9 fields)

Per #7 (8 fields) + #11's `phase` extension:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | yes | Namespaced, e.g. `ai-fluency/foundation-vs-finetuned` |
| `gap` | string | yes | Track name: `AI technical fluency` |
| `concept` | string | yes | One-line description of the concept |
| `difficulty` | enum | yes | `easy` \| `medium` \| `hard` |
| `source` | list | yes | ≥1 source entry (see §3.1). Must include ≥1 primary. |
| `related_gaps` | list | yes | Cross-track links (e.g. `[interview-readiness]`). Can be empty. |
| `prerequisites` | list | yes | List of node `id`s forming the DAG. Empty for root. |
| `challenge_types` | list | yes | Subset of `[concept-recall, scenario, technical-deep-dive]` |
| `phase` | enum | yes | `1` (active in SR loop) \| `2` (authored, parked) |

### 3.1 Source entry schema

Each entry in the `source` list:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `url` | string | yes | Primary source URL. For pasted text, `pasted:<sha8>` with blob in `sources/<sha8>.txt` |
| `type` | enum | yes | `model-card` \| `blog` \| `paper` \| `docs` \| `report` \| `pasted` |
| `accessed_at` | date | yes | ISO date (YYYY-MM-DD) |
| `anchor` | string | yes | Short quoted phrase from the source the concept is grounded in |

## 4. The 21 target concept nodes

The agent authors proposals targeting these 21 nodes (from #11's finalized list). Each proposal must match the `id` and `concept` intent; the agent fills the other fields from the sources.

| id | concept (one line) | prerequisites |
|----|-------------------|---------------|
| `ai-fluency/foundation-vs-finetuned` | Pretrained foundation models vs task-specific fine-tuned models | _(root)_ |
| `ai-fluency/transformer-architecture-basics` | Transformers, attention, tokens | `foundation-vs-finetuned` |
| `ai-fluency/training-pipeline` | Pretraining → SFT → RLHF/DPO | `transformer-architecture-basics` |
| `ai-fluency/reading-model-reports` | How to read a GPT-4/Claude/Gemini report | `training-pipeline` |
| `ai-fluency/context-windows` | What a context window is, why it grew | `foundation-vs-finetuned` |
| `ai-fluency/long-context-vs-rag` | When long-context makes RAG unnecessary vs when RAG wins | `context-windows`, `rag-fundamentals` |
| `ai-fluency/prompting-techniques` | CoT, few-shot, system prompts, structured outputs | `foundation-vs-finetuned` |
| `ai-fluency/rag-fundamentals` | RAG — retrieve chunks, stuff context, generate | `prompting-techniques` |
| `ai-fluency/fine-tuning-when-why` | When to fine-tune vs prompt vs RAG | `rag-fundamentals`, `training-pipeline` |
| `ai-fluency/llm-wiki-knowledge-compounding` | Karpathy LLM-Wiki pattern — compile once vs retrieve per query | `rag-fundamentals` |
| `ai-fluency/why-evals-matter` | Goodhart's law, MMLU/HumanEval, custom evals | `foundation-vs-finetuned` |
| `ai-fluency/eval-design` | Custom evals — golden sets, rubric grading, regression suites | `why-evals-matter` |
| `ai-fluency/llm-as-judge` | LLMs grading LLMs — same-model trap, position bias | `eval-design` |
| `ai-fluency/human-eval-vs-automated` | When human judgment vs automated evals suffice | `llm-as-judge` |
| `ai-fluency/inference-cost-economics` | Cost-per-query, token economics, $/1M-token model | `foundation-vs-finetuned` |
| `ai-fluency/latency-aware-design` | TTFT, throughput, streaming — latency shapes UX | `inference-cost-economics` |
| `ai-fluency/reading-model-cards` | What to look for in a model card | `training-pipeline` |
| `ai-fluency/model-routing` | Cheap/strong tier routing, fallback ladders, cost caps | `inference-cost-economics`, `fine-tuning-when-why` |
| `ai-fluency/hallucination-causes-mitigations` | Why LLMs hallucinate + mitigation stack | `rag-fundamentals`, `context-windows` |
| `ai-fluency/ai-safety-basics` | Alignment, RLHF, constitutional AI, safety filters | `training-pipeline`, `hallucination-causes-mitigations` |
| `ai-fluency/prompt-injection-security` | Adversarial inputs — direct, indirect via RAG/tools, jailbreaks | `prompting-techniques`, `rag-fundamentals` |

All 21 default to `phase: 1`. The phase split (activate 20, park extras) happens at review time, not authoring time.

## 5. The 6 critic gates (Sonnet)

Each gate is a **concrete, checkable rule**. The critic runs all 6 on every Haiku proposal. A proposal failing any gate gets a `# critic: FLAG — <reason>` comment and is still written to staging (Manmeet decides). A proposal passing all gates gets `# critic: PASS`.

### Gate 1: Groundedness

**Rule:** Every claim in the `concept` field must be supported by the cited source's `anchor` quote. The anchor must appear (verbatim or near-verbatim) in the fetched source content.

**Check:** Does the anchor string exist in the source text? If not, FLAG with `anchor not found in source`.

**Pass:** Anchor found, concept follows from anchor.

### Gate 2: Primary-citation

**Rule:** The `source` list must include ≥1 entry where `type` is `model-card`, `paper`, `docs`, or `report` (primary tier). Secondary (`blog`) and tertiary (`pasted`) can supplement but not be sole citation.

**Check:** Is there ≥1 primary-tier source? If not, FLAG with `needs primary source`.

**Pass:** ≥1 primary source present.

### Gate 3: Tier-mix annotation

**Rule:** Annotate the node with the source tier mix.

**Output:** `# critic: <N> primary, <M> secondary, <K> tertiary` (count per tier).

This is informational, not pass/fail — but if a node has 0 primary, Gate 2 already flagged it.

### Gate 4: Stability + recency

**Rule:** Each node tagged `stability: foundational` or `stability: evolving`.
- **Foundational** concepts (transformer architecture, RLHF mechanism, attention) accept older citations.
- **Evolving** concepts (context window sizes, model capabilities, pricing) require the most recent primary source available in the corpus.

**Check:** For evolving concepts, is the cited primary source the most recent one the agent fetched? If a newer source exists in the corpus and isn't cited, FLAG with `stale — superseded by <newer source URL>`.

**Pass:** Stability tagged; for evolving, most-recent source cited.

### Gate 5: Scope triage (two-axis test)

**Rule:** Every proposal must pass the two-axis test:
- Axis 1: explains *how the tech works* (not *how to ship with it*).
- Axis 2: *conceptual literacy* (not *craft skill*).

**Check:** Does the concept explain how AI technology works at a literacy level? If it's about shipping/product design, FLAG with `defer to Phase 2: AI Product Judgment`. If it's PM craft (PRD writing, prioritization), FLAG with `defer to Phase 2: PM Fundamentals`. If it's news/announcement (not a concept), FLAG with `not a concept — extract underlying principle`.

**Pass:** Concept is technical-fluency literacy.

### Gate 6: Reference-framework gap check

**Rule:** Cross-check the proposal against `sources/reference-framework-inputs/` (JDs + interview questions).

**Check:** Read the 10 JDs and the interview-questions doc. Extract the technical-fluency concepts each names. For the node being critiqued, is it covered by the reference framework?

**Output:** `# critic: reference-framework: covered by <N>/10 JDs` (how many JDs name this concept or a close synonym).

**Additional check:** After all 21 nodes are drafted, run a final gap pass: are there concepts named in ≥2 JDs that don't appear in any of the 21 nodes? If yes, FLAG each as `# critic: GAP — JDs name <concept> but no node covers it; add or consciously defer`.

## 6. Haiku draft prompt

The Haiku draft call takes the fetched source content + the 21-node target list and produces proposals. Prompt structure:

```
You are drafting concept nodes for an AI Technical Fluency curriculum.

Source content (fetched):
<source text or excerpt>

Target concept nodes (author proposals for any that this source grounds):
<the 21-node table from §4>

For each target node that this source grounds, produce a YAML proposal with all 9 fields.
The `anchor` must be a verbatim phrase from the source text.
Only propose nodes the source actually grounds — do not invent concepts.
If the source doesn't ground any node, return an empty list.
```

Haiku returns YAML proposals. The agent parses them and passes each to Sonnet for the critic gates.

## 7. Sonnet critic prompt

```
You are the critic for AI Technical Fluency concept-node proposals.

Source content (the fetched source the proposal is grounded in):
<source text>

Proposal:
<yaml node>

Reference framework (JDs + interview questions):
<extracted concepts from reference-framework-inputs/>

Run these 6 gates. For each, output PASS or FLAG — <reason>:
1. Groundedness: does the anchor exist verbatim in the source?
2. Primary-citation: is there ≥1 primary-tier source?
3. Tier-mix: how many primary/secondary/tertiary?
4. Stability + recency: tag foundational|evolving; for evolving, is this the most recent source?
5. Scope triage: is this technical-fluency literacy (not product/craft/news)?
6. Reference-framework: how many of 10 JDs name this concept?

Output the annotated YAML with `# critic:` comments inline.
```

## 8. File structure (what to build)

```
learning_bot/
├── ingestion_agent/
│   ├── __init__.py
│   ├── cli.py              # argparse entrypoint: ingest <path-or-url> | --all <dir>
│   ├── fetcher.py           # read files, fetch URLs, one-hop links, PDF extraction, gh api README
│   ├── drafter.py           # Haiku draft call (§6 prompt)
│   ├── critic.py            # Sonnet critic call (§7 prompt, 6 gates)
│   ├── schema.py            # dataclass / pydantic model for the 9-field node + source entry
│   ├── writer.py            # write curriculum/ai-technical-fluency.staging.yaml with critic comments
│   └── reference.py         # load + parse reference-framework-inputs/ for Gate 6
├── tests/
│   ├── test_fetcher.py      # test URL fetch, PDF extraction, one-hop, gh api (mock)
│   ├── test_drafter.py      # test Haiku call with mocked response
│   ├── test_critic.py       # test each of the 6 gates with sample proposals
│   └── test_writer.py       # test YAML output format with critic comments
├── requirements.txt         # anthropic, requests, pypdf, tenacity, pyyaml, pydantic
└── sources/                 # already populated — read-only
```

## 9. Dependencies

```
anthropic>=0.40.0      # Anthropic SDK (per #5: Anthropic direct)
requests>=2.31.0       # URL fetching (no JS, no auth)
pypdf>=4.0.0           # PDF text extraction
tenacity>=8.0.0        # retries on transient API failures (Task_IQ pattern, #4)
pyyaml>=6.0            # YAML output
pydantic>=2.0          # schema validation for the 9-field node
pytest>=7.0            # tests
```

## 10. Environment

- Python 3.11+ (verify with `python --version`)
- `ANTHROPIC_API_KEY` in `.env` (already present)
- `gh` CLI authenticated (for GitHub README fetches — `gh auth status`)
- Run from repo root: `python -m ingestion_agent ingest <path-or-url>`

## 11. Validation (done-when for the implementer)

The implementer is done when:

1. **`ingestion_agent/` exists** with the 6 modules in §8, each ≤200 lines.
2. **`python -m ingestion_agent ingest sources/primary/anthropic-claude.url`** runs without error, fetches the URL, and produces ≥1 proposal in `curriculum/ai-technical-fluency.staging.yaml`.
3. **`python -m ingestion_agent ingest --all sources/`** runs without error, processes every file in `sources/` (skipping `reference-framework-inputs/`), and produces proposals for the 21 target nodes (some may be empty if no source grounds them).
4. **All 6 critic gates run** on every proposal — verify by reading the `# critic:` comments in the staging YAML.
5. **Tests pass:** `pytest tests/` — fetcher, drafter, critic (each gate), writer.
6. **The staging YAML is valid YAML** — `python -c "import yaml; yaml.safe_load(open('curriculum/ai-technical-fluency.staging.yaml'))"` succeeds.
7. **No auto-commit** — the agent writes to `curriculum/ai-technical-fluency.staging.yaml` only; it does NOT run `git add` or `git commit`. Manmeet reviews and promotes manually (per #3).

## 12. Out of scope for the implementer

- **Do NOT build the curriculum YAML content** — the agent produces proposals; Manmeet reviews and edits. The implementer builds the *tool*, not the *output*.
- **Do NOT build the bot, SR loop, grader, or Telegram integration** — those are separate Phase 1 work.
- **Do NOT build the autonomous fetcher** — that's Phase 2 (ruled out of scope on the map). This agent ingests what Manmeet feeds it.
- **Do NOT recurse beyond one-hop** when following links.
- **Do NOT auto-commit** anything. The staging file is the only output; git operations are Manmeet's.

## 13. Notes for the implementer

- **Read `CREDITS.md`** for the source tier list and which sources are primary/secondary/tertiary.
- **Read `curriculum/README.md`** for the schema and review-gate context.
- **Read `sources/README.md`** for the corpus structure and accepted formats.
- **The 21 target nodes are fixed** (§4) — the agent proposes content for them, it does not invent new node IDs.
- **If a source doesn't ground any node**, the agent logs `"source <X> grounded 0 nodes"` and moves on. Not every source maps to every node.
- **Multiple sources can ground the same node** — the agent merges proposals, keeping the strongest anchors and the best tier mix.
- **The `phase` field defaults to `1`** for all 21 nodes. The split to activate 20 + park extras happens at Manmeet's review, not in the agent.
