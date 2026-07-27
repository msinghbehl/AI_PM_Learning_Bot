# Reference framework inputs — AI PM job descriptions

This subfolder holds the **reference artifacts** the ingestion agent's critic uses for the completeness gap-check (one of the 6 critic gates from #11's decisions). These are NOT ingested as concept sources — they're cross-checked against the proposed concepts to flag gaps.

## What goes in here

**3-5 real AI PM job descriptions** from companies that hire for this role. The critic reads these and flags: *"your corpus surfaced N concepts; these JDs also name X, Y, Z which you haven't hit — add as a node or consciously defer."*

### Suggested JDs to gather

Aim for a mix of company stages so the reference framework captures the full surface:

- **Big tech:** Meta (AI PM), Google (AI/ML PM), Microsoft (AI PM) — names what large-org AI PMs are probed on
- **AI-native:** OpenAI, Anthropic, Scale AI — names what frontier-lab PMs need
- **Startup:** a Series B/C AI startup JD — names what generalist AI PMs at smaller orgs need

### Current contents

```
reference-framework-inputs/
├── ai_pm_jobs/                       ← 10 AI PM JDs (clean .md files)
│   ├── Apple_AI_PM_JD_2026-07-26.md
│   ├── DeepMind_AI_PM_JD_2026-07-26.md
│   ├── IBM_Research_AI_PM_JD_2026-07-26.md
│   ├── Intel_AI_PM_JD_2026-07-26.md
│   ├── Meta_AI_PM_JD_2026-07-26.md
│   ├── NVIDIA_AI_PM_JD_2026-07-26.md
│   ├── OpenAI_AI_PM_JD_2026-07-26.md
│   ├── Salesforce_Einstein_AI_PM_JD_2026-07-26.md
│   ├── Tesla_AI_PM_JD_2026-07-26.md
│   └── Uber_AI_PM_JD_2026-07-26.md
└── ai-pm-interview-guidance.md       ← 8 categories of technical AI PM interview questions
```

### Cleanup notes (2026-07-26)

- **`AI PM Interview Guidance.rtf`** → converted to `ai-pm-interview-guidance.md` (RTF not agent-ingestible).
- **`Technical AI PM questions.jpeg`** → removed (redundant with the transcribed markdown; the JPEG was the infographic referenced in the RTF, and the agent can't read images).

### Coverage

10 JDs exceeds the 3-5 target — that's fine, more signal for the critic's gap-check. Coverage spans:
- **Big tech:** Meta, Apple, Intel, IBM, Salesforce, Uber, Tesla
- **AI-native:** OpenAI, DeepMind, NVIDIA

The interview-guidance doc adds a second signal: the 8 question categories (transformers, agents/MCP, routing, LLM fundamentals, RAG, system design, company-specific, evals) map directly to the 21 concept nodes and give the critic a second completeness check beyond the JDs.
