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
├── GenerativeAICourse/              ← 14 lesson .md files (LLMs, RAG, agents, evals, LLMOps)
├── agents-towards-production/        ← README only (notebooks removed — not agent-ingestible)
├── linkedin_resources/               ← LinkedIn saves, organized by category + MASTER_INDEX.md
│   ├── ai_pm_skills/
│   ├── career_advice/
│   ├── claude_code/
│   ├── free_resources/
│   └── github_repos/                 ← .md files (NOTE: 3 have placeholder URLs — fill in real repos)
├── AI PM Knowledge Store & Deep Multi-Hop Extraction Plan.md  ← synthesis doc (secondary — pointer layer)
└── reference-framework-inputs/       ← AI PM JDs + interview questions (NOT ingested as concepts)
```

### Tier mix (per #11's decisions)

- **Primary** (`primary/`): 5 sources — Anthropic, OpenAI, Google DeepMind docs/reports + 2 foundational arXiv papers. Every concept node must cite ≥1 of these.
- **Secondary** (`GenerativeAICourse/`, `agents-towards-production/README.md`, synthesis doc): practitioner-authored course material and synthesis. Supplements primary, never sole citation.
- **Tertiary** (`linkedin_resources/`): LinkedIn posts pointing at primary sources. Recorded as provenance, not as citations.
- **Reference framework** (`reference-framework-inputs/`): JDs + interview questions. NOT ingested as concepts — the critic cross-checks against these for completeness gaps.

### Known gaps

All previously identified gaps are closed (2026-07-26):
- ✅ GitHub repo references now point to real repos (GenerativeAICourse, Microsoft generative-ai-for-beginners, NirDiamant/agents-towards-production).
- ✅ Karpathy LLM Wiki gist saved locally as `karpathy-llm-wiki.md` (primary source for concept node #10).
- ✅ Practitioner blog post added (Simon Willison on GPT-5.6 family — secondary source for model reports, context windows, cost economics).

The corpus is ready for the ingestion agent.

### What does NOT go in here

- **AI PM job descriptions** → those go in `sources/reference-framework-inputs/` (different purpose — the critic cross-checks against them for completeness gaps, not ingests them as concepts).
- **The curriculum YAML** → that's output, goes in `curriculum/`.
- **The ingestion agent code** → goes in the repo root or a `src/` dir when built (separate from sources).

## Provenance

Every file here is recorded by the agent as provenance ("Manmeet encountered this concept via X") when it cites a primary source the file pointed at. The corpus entry itself is never the citation on a concept node — the primary source it points to is.
