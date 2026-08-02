# Sources — corpus for the ingestion agent

This is the **immutable raw layer** the ingestion agent reads from when authoring the AI Technical Fluency curriculum (ticket #11). It maps to the LLM Wiki's "raw sources" layer — the agent reads from here but never modifies it.

## What goes in here

Your corpus — anything you've encountered that teaches an AI Technical Fluency concept. The agent follows one-hop links found inside these sources (per the #11 interface decision), so you don't need to pre-flatten nested references, but the *entry points* live here.

### Accepted formats

- **Pasted text** — `.txt` or `.md` files. Use for LinkedIn posts, Slack threads, notes you've taken. Filename convention: `<author>-<topic>.md` (e.g., `karpathy-llm-wiki.md`).
- **URLs** — save as a `.url` file with the URL on the first line, followed by context/notes. The agent fetches with `requests` (no JS, no auth). If a URL 401s or needs JS, paste the content as a `.md` file instead.
- **PDFs** — `.pdf` files. The agent extracts text with `pypdf`. Use for model reports, arXiv papers, whitepapers.
- **GitHub repos** — save the repo URL in a `.url` or `.md` file. The agent fetches the README via `gh api`, not a full clone.

### Current corpus structure

```
sources/
├── primary/                          ← PRIMARY sources (model creators + cited arXiv)
│   ├── anthropic-claude.url          ← Claude model family (context, safety, tool use)
│   ├── openai-gpt4-report.url        ← GPT-4 technical report (training, evals, model card)
│   ├── google-gemini-report.url      ← Gemini (MoE, long context, multimodal)
│   ├── arxiv-attention-is-all-you-need.url  ← Transformer architecture (foundational)
│   └── arxiv-rlhf-instructgpt.url    ← RLHF paper (alignment, training pipeline)
├── GenerativeAICourse/              ← 13 lesson .md files (LLMs, RAG, agents, evals, LLMOps)
│   └── lessons/                      ← 01_intro through 21_future
├── GenerativeAICourse_README.md      ← Course README (fetched from GitHub)
├── agents-towards-production_README.md ← 28-tutorial agents repo README (fetched from GitHub)
├── karpathy-llm-wiki.md              ← Karpathy's LLM Wiki idea doc (primary for concept node #10)
├── linkedin_resources/               ← 35 files: LinkedIn saves organized by category
│   ├── MASTER_INDEX.md               ← Full index with status, fetchability, duplication notes
│   ├── ai_pm_skills/                 ← 15 files (full content): learning paths, glossary, skills, interviews
│   ├── career_advice/                ← 3 files: salary benchmarks, interview ranking, 90-day plan
│   ├── claude_code/                  ← 4 files: Claude Code OS, learning doc, optimization
│   ├── free_resources/               ← 10 files: Stanford courses, Anthropic courses, GitHub repos, Simon Willison
│   └── github_repos/                  ← 3 .url pointers (GenerativeAI, Microsoft, agents-towards-production)
├── AI PM Knowledge Store & Deep Multi-Hop Extraction Plan.md  ← synthesis doc (secondary — pointer layer)
└── reference-framework-inputs/       ← AI PM JDs + interview questions (NOT ingested as concepts)
    ├── ai_pm_jobs/                   ← 10 AI PM JDs (Apple, DeepMind, IBM, Intel, Meta, NVIDIA, OpenAI, Salesforce, Tesla, Uber)
    ├── ai-pm-interview-guidance.md   ← 8 categories of technical AI PM interview questions
    └── README.md
```

### Tier mix (per #11's decisions)

- **Primary** (`primary/`): 5 sources — Anthropic, OpenAI, Google DeepMind docs/reports + 2 foundational arXiv papers. Every concept node must cite ≥1 of these.
- **Secondary** (`GenerativeAICourse/`, `agents-towards-production_README.md`, `karpathy-llm-wiki.md`, `simon-willison-gpt5-family.md`, synthesis doc): practitioner-authored course material, blog analysis, and synthesis. Supplements primary, never sole citation.
- **Tertiary** (`linkedin_resources/`): 35 LinkedIn posts organized by category. Points at primary sources. Recorded as provenance, not as citations.
- **Reference framework** (`reference-framework-inputs/`): 10 JDs + interview questions. NOT ingested as concepts — the critic cross-checks against these for completeness gaps.

### Known gaps

All previously identified gaps are closed (2026-08-01):
- ✅ GitHub repo references point to real repos (GenerativeAICourse, Microsoft generative-ai-for-beginners, NirDiamant/agents-towards-production).
- ✅ Karpathy LLM Wiki gist saved locally as `karpathy-llm-wiki.md` (primary source for concept node #10).
- ✅ Simon Willison GPT-5.6 analysis fetched and saved as full `.md` (secondary source for model reports, context windows, cost economics).
- ✅ LinkedIn resources expanded from 12 stubs to 35 files (30 full content, 3 stubs, 3 .url pointers) — see `linkedin_resources/MASTER_INDEX.md` for the full index.
- ✅ Duplicate files removed (`AI_Agentic_Builder.md`, `Stub_files.md`, 2 replaced stubs).
- ✅ Nested `agents-towards-production/` stub folder removed — real content is in root-level `agents-towards-production_README.md`.

The corpus is ready for the ingestion agent.

### What does NOT go in here

- **AI PM job descriptions** → those go in `sources/reference-framework-inputs/` (different purpose — the critic cross-checks against them for completeness gaps, not ingests them as concepts).
- **The curriculum YAML** → that's output, goes in `curriculum/`.
- **The ingestion agent code** → goes in the repo root or a `src/` dir when built (separate from sources).

## Provenance

Every file here is recorded by the agent as provenance ("Manmeet encountered this concept via X") when it cites a primary source the file pointed at. The corpus entry itself is never the citation on a concept node — the primary source it points to is.
