# Plan — AI PM Learning Bot ("Coach")

> A personalized daily learning coach that closes the gaps between Manmeet's current
> profile (AI TPM, IC3 L61) and the ideal AI Product Manager profile ($500K+ TC target).
> Built in two phases: lean MVP to validate the learning loop, then refactor into a
> portfolio-grade repo that itself becomes evidence of AI PM thinking.

---

## 1. Why this bot exists

The `ideal-profile.md` gap map names six gaps to close before the $500K move is
realistic:

| Gap | Bot's role in closing it |
|-----|--------------------------|
| AI technical fluency | Daily AI concept + technical deep-dive challenges |
| PM product judgment | PRD/spec writing challenges graded against real rubrics |
| Public evidence of thinking | (Optional add-on) writing prompts from daily learnings |
| Interview readiness | Scenario/case questions build the "greatest hits" story bank |
| Cross-org leadership | Scenario questions framed around real cross-functional conflicts |
| Impact at scale | Curriculum ties concepts to shipped-product scale, not internal tools |

The bot is **not** a generic "learn AI" tool. Its curriculum is reverse-engineered from
the ideal profile — every concept maps to a gap, every challenge maps to a competency a
hiring manager at Meta / OpenAI / a Series B startup will probe.

---

## 2. Product principles

1. **Goal-anchored, not topic-anchored.** Every learning unit traces to a gap in
   `ideal-profile.md`. No "AI news of the day" filler.
2. **Active recall over passive reading.** The bot asks; you answer. It grades; you
   re-encounter what you got wrong. Spaced repetition, not a newsletter.
3. **Quality at low cost.** A cheap model generates; a strong model verifies and grades.
   Guardrails (rubrics, schema validation, citation checks) keep quality high without
   paying Sonnet/Opus prices for every token.
4. **Self-improving.** The bot tracks what you get wrong, regenerates similar
   challenges, and ingests new AI PM concepts from curated sources on a schedule.
5. **Itself a portfolio piece.** Phase 2 treats the repo as evidence: PRDs, ADRs,
   evals, a public write-up. The bot that teaches you AI PM is itself an AI PM artifact.

---

## 3. Decisions (from brainstorming session)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Delivery channel | **Telegram** | Matches Task_IQ / FullPotential stack; mobile-first; simple bot API |
| LLM backbone | **Model routing + guardrails** | Cheap model (Haiku / GPT-4o-mini / Gemini Flash) for generation & drafting; strong model (Sonnet / GPT-4 / Opus) as verifier + grader. Quality via rubrics + schema + critic pass, not via expensive model on every call |
| Cadence | **30 min/day, balanced** | 1 PM concept + 1 AI concept + 1 challenge, daily |
| Challenge formats | Concept recall, Scenario/case, PRD/spec writing, Technical deep-dives | Covers fluency + judgment + shipping + technical credibility |
| Self-improvement | **Curated sources + scheduled fetch** | Fixed list (Anthropic/OpenAI/DeepMind blogs, model release notes, HN, AI PM newsletters) fetched on schedule, summarized by cheap model, integrated by strong model |
| Progress tracking | **SQLite (logic) + Google Sheet (mirror)** | SQLite owns spaced-repetition state + mastery scoring; Sheet is the human-readable dashboard, queryable in Looker/Sheets |
| Build approach | **Phased: lean MVP → portfolio-grade** | Validate the pedagogy loop first, then refactor into evidence |

---

## 4. Architecture (Phase 1 — Lean MVP)

```
┌──────────────────────────────────────────────────────────────┐
│                        Telegram (user)                        │
└───────────────┬──────────────────────────────────┬───────────┘
                │ /start, /today, /answer, /stats   │ daily push
                ▼                                    ▼
┌─────────────────────────────────┐  ┌──────────────────────────┐
│        Bot orchestrator         │  │   Scheduler (cron/APScheduler)│
│   (Python, single entrypoint)  │  │  - 7am: push daily lesson │
│  - command routing             │  │  - weekly: fetch sources  │
│  - state machine per user      │  │  - nightly: grade + SR    │
└───────────────┬─────────────────┘  └──────────────┬───────────┘
                │                                    │
        ┌───────▼────────┐                 ┌────────▼─────────┐
        │  Model router   │                 │  Source fetcher  │
        │  (guardrails)   │                 │  (curated list)  │
        └───┬────────┬────┘                 └────────┬─────────┘
            │        │                               │
   ┌────────▼─┐ ┌──▼───────────┐          ┌────────▼─────────┐
   │ Cheap LLM│ │ Strong LLM   │          │ Summarizer (cheap)│
   │ generate │ │ verify+grade  │          │ → new concepts    │
   └──────────┘ └──────────────┘          └───────────────────┘
            │
        ┌───▼────────────────────┐
        │  SQLite (state)        │
        │  - mastery scores      │
        │  - SR schedule          │
        │  - challenge history    │
        └───────────┬────────────┘
                    │ mirror (nightly)
                ┌───▼────────────┐
                │  Google Sheet  │
                │  (dashboard)    │
                └────────────────┘
```

### 4.1 Model routing & guardrails (the cost/quality lever)

This is the core design decision. Quality comes from **structure + verification**, not
from using the most expensive model on every call.

**Generation tier (cheap model — Haiku / GPT-4o-mini / Gemini Flash):**
- Draft daily lesson (concept explanation + example)
- Generate concept-recall questions
- Generate scenario/case question stems
- Summarize fetched sources
- Draft PRD-writing prompt

**Verification tier (strong model — Sonnet / GPT-4 / Opus, called sparingly):**
- **Critic pass** on generated content before it reaches the user (catches errors,
  hallucinations, weak questions)
- **Grader** for free-text answers and PRDs (rubric-based, structured output)
- **Curriculum integrator** — decides whether a fetched-and-summarized concept is worth
  adding to the curriculum and where it fits
- **Regenerator** — when you get a question wrong, the strong model designs a *similar
  but different* challenge to re-test the concept

**Guardrails (model-agnostic):**
- **JSON schema validation** on every LLM output — reject + retry on schema violation
- **Rubric objects** stored in the repo (versioned) — grading always references a rubric
  ID, never a free-form prompt
- **Citation check** — fetched-source learnings must cite the source URL; critic rejects
  unsourced claims
- **Difficulty calibration** — questions tagged Easy/Medium/Hard; bot tracks your
  pass rate per tier and adjusts the mix
- **Cost ledger** — every call logs model + tokens + cost; daily/weekly budget caps
  trigger fallback to cheaper model or skip

**Expected cost profile:** ~80% of calls on cheap model, ~20% on strong model. With
Haiku at ~$1.25/M in and Sonnet at ~$3/M in, a daily 30-min session should land well
under $0.50/day, likely $0.10–0.20/day once the curriculum is seeded.

### 4.2 Curriculum structure

The curriculum is a **versioned JSON/YAML tree** in the repo, not free-form LLM output.
Each node:

```yaml
- id: ai-fluency/evals/why-evals-matter
  gap: AI technical fluency
  concept: "Why evals matter in AI products — Goodhart's law, MMLU/HumanEval, custom evals"
  difficulty: medium
  source: ideal-profile.md#ai-technical-fluency
  related_gaps: [interview-readiness]
  prerequisites: [ai-fluency/foundation-vs-finetuned]
  challenge_types: [concept-recall, scenario, technical-deep-dive]
```

**Top-level tracks (mapped to gaps):**
1. **AI Technical Fluency** — foundation vs fine-tuned models, RAG vs prompting vs
   fine-tuning tradeoffs, evals, inference cost/latency, context windows, model cards,
   architecture literacy (read 3-4 major model reports)
2. **PM Fundamentals** — PRD writing, prioritization frameworks, user research methods,
   metrics & measurement, roadmap/OKR planning, stakeholder alignment
3. **AI Product Judgment** — AI-native UX patterns, latency-aware design, failure-mode
   design (hallucinations, safety), build-vs-buy for AI, cost-per-query economics
4. **Interview Readiness** — behavioral STAR stories, PM case studies, AI PM-specific
   cases ("design Copilot for X"), greatest-hits portfolio building
5. **Cross-Functional Leadership** — influencing without authority, conflict resolution,
   planning cycles, exec communication

### 4.3 Daily loop (30 min)

```
7:00am  Push: today's lesson
        ├─ PM concept (2-3 min read)
        ├─ AI concept (2-3 min read)
        └─ Challenge of the day (rotates: recall / scenario / PRD / deep-dive)

User answers throughout the day (async)

Nightly:
  ├─ Grade answers (strong model, rubric)
  ├─ Update mastery score per concept
  ├─ Schedule spaced-repetition re-asks for missed concepts
  └─ Mirror to Google Sheet
```

### 4.4 Spaced repetition & self-improvement

- **SR algorithm:** SM-2 variant (like Anki) — each concept has an ease factor and
  interval; wrong answers reset interval, right answers lengthen it.
- **Re-ask generation:** when a concept is due, the **strong model** generates a
  *different* challenge targeting the same concept (not the same question) — this is
  where "build similar challenges to test that concept again" lives.
- **Mastery score:** per-concept 0–100; per-track rollup; overall readiness score
  surfaced in `/stats`.
- **New concept ingestion:** weekly, the source fetcher pulls curated sources → cheap
  model summarizes → strong model decides fit + inserts into curriculum tree with a
  prerequisite link.

### 4.5 Curated source list (seed, extensible)

- Anthropic blog / model cards / system prompts
- OpenAI blog / model release notes
- Google DeepMind blog
- HN (AI-tagged, top stories)
- Stratechery / Latent Space / The Gradient
- AI PM-specific: Lenny's Newsletter (AI product cases), Reforge AI product content
- Model release notes on HuggingFace
- ArXiv (curated: only papers cited by the above)

---

## 5. Phase 1 — Lean MVP scope

**Goal:** validate the daily learning loop + grading + SR re-ask actually works for
*you*, before investing in portfolio-grade structure.

**In scope:**
- Single Python file or small module (`bot.py` + `curriculum.py` + `grader.py`)
- Telegram bot via `python-telegram-bot`
- SQLite (no ORM, raw schema)
- Model router with 2 tiers (Haiku + Sonnet via Anthropic API — you already have keys)
- 1 track seeded (AI Technical Fluency, ~20 concepts) — enough to run for 3-4 weeks
- Concept-recall + scenario challenges only (PRD grading comes in Phase 2 — it needs the
  rubric harness to be worth building)
- `/today`, `/answer`, `/stats`, `/explain` commands
- Nightly grading job (cron or APScheduler)
- Cost ledger (simple — log every API call)

**Out of scope (Phase 2):**
- Google Sheet mirror
- PRD/spec grading
- Source fetcher + auto-curriculum-ingestion
- Public repo / PRDs / ADRs / evals
- Multi-user (it's just you)

**Done =** you've used it daily for 2 weeks, the SR re-asks actually surface things you
got wrong, and the grading feels fair. If after 2 weeks it doesn't feel useful, we
revisit the design before building Phase 2.

---

## 6. Phase 2 — Portfolio-grade refactor

**Trigger:** Phase 1 validated the loop for 2+ weeks.

**Upgrade to:**
- Proper repo structure (see §7)
- PRD for the bot itself (this becomes a writing sample)
- 3–4 ADRs (model routing, SR algorithm, guardrails design, curriculum schema)
- Full curriculum across all 5 tracks (~100 concepts)
- PRD/spec grading with rubric harness
- Google Sheet mirror + dashboard
- Source fetcher + auto-ingestion
- Eval suite for the bot itself (does it grade fairly? does it generate good questions?
  measured against a held-out set)
- Public write-up / LinkedIn post on the design ("How I built a self-improving AI PM
  coach for $0.15/day") — closes the public-evidence gap

**This phase is itself the portfolio piece.** The repo, the PRD, the ADRs, the evals,
and the write-up are all evidence of AI PM thinking that hiring managers can find.

---

## 7. Target repo structure (Phase 2)

```
learning_bot/
├── README.md
├── PLAN.md                      # this file
├── PRD.md                        # product spec for the bot
├── docs/adr/                     # architecture decision records
│   ├── 0001-model-routing.md
│   ├── 0002-spaced-repetition.md
│   ├── 0003-guardrails-and-rubrics.md
│   └── 0004-curriculum-schema.md
├── src/
│   ├── bot.py                    # Telegram entrypoint
│   ├── orchestrator.py          # command routing, state machine
│   ├── model_router.py          # cheap/strong tier + guardrails
│   ├── grader.py                 # rubric-based grading
│   ├── curriculum.py            # load/serve curriculum tree
│   ├── sr.py                     # spaced-repetition scheduler
│   ├── fetcher.py               # curated source ingestion
│   ├── sheet_mirror.py          # SQLite → Google Sheet
│   └── cost_ledger.py           # API cost tracking
├── curriculum/                  # versioned YAML curriculum
│   ├── ai-fluency.yaml
│   ├── pm-fundamentals.yaml
│   ├── ai-product-judgment.yaml
│   ├── interview-readiness.yaml
│   └── cross-functional-leadership.yaml
├── rubrics/                     # versioned grading rubrics
│   ├── concept-recall.yaml
│   ├── scenario-case.yaml
│   ├── prd-writing.yaml
│   └── technical-deepdive.yaml
├── data/
│   └── coach.db                  # SQLite
├── evals/                       # bot self-eval suite
│   ├── grading_accuracy/
│   └── question_quality/
└── tests/
```

---

## 8. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Grading feels unfair / inconsistent | Rubric-anchored grading + critic pass; Phase 2 adds an eval suite measuring grader agreement |
| Cost creeps up | Cost ledger + daily/weekly caps; fallback to cheaper model on cap hit |
| Curriculum goes stale | Weekly source fetch + strong-model integrator; curriculum is versioned in repo |
| You stop using it | 30-min cap; async answering; SR re-asks keep it from feeling repetitive; 2-week Phase 1 validation before Phase 2 investment |
| Bot generates wrong AI facts | Critic pass (strong model) on every generated lesson before it reaches you; citation requirement for source-derived content |
| Over-engineering before validating | Phase 1 is deliberately small — single track, 2 challenge types, no Sheet, no fetcher |

---

## 9. Open questions to resolve before Phase 1 build

1. **Anthropic API key + budget** — confirm you have a key and a monthly cap you're
   comfortable with (suggest $20/mo cap; expected actual ~$3–6/mo).
2. **Telegram bot token** — you have one from Task_IQ; reuse or create a new bot
   (`@ai_pm_coach` or similar).
3. **Where does it run?** — local machine (laptop) with cron, or a cheap host
   (Railway / Fly / a Raspberry Pi)? Local is fine for Phase 1 since it's just you.
4. **Time zone** — Pacific for the 7am push?
5. **First track confirmation** — AI Technical Fluency as the Phase 1 seed track, or do
   you want PM Fundamentals first? (My recommendation: AI Fluency — it's your biggest
   gap and the most differentiating for AI PM roles.)

---

## 10. What I will NOT build yet (per your instruction)

- No code in this pass — this is the plan only.
- No PRD, ADRs, or repo scaffolding until you sign off on the plan.
- Once you approve, Phase 1 build is a separate session.
