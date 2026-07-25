# Pedagogy Model — Coach

> The canonical statement of *how Coach teaches*. Read this before designing the
> grading loop, the spaced-repetition scheduler, the curriculum, or any challenge
> format. For *why a specific choice was made*, see the cross-linked ADRs.

This decision was resolved in
[Pedagogy model: which learning-science principles are load-bearing for Coach?](https://github.com/msinghbehl/AI_PM_Learning_Bot/issues/2).

---

## 1. North star

**Storage strength is the primary goal; fluency is a deliberate secondary.**

The destination is interview and on-the-job performance, which requires *durable*
retrieval of concepts and stories first. You cannot reason fluently in an interview
about RAG-vs-finetuning tradeoffs if the base knowledge isn't durable. Fluency
(novel-scenario reasoning) is then trained *on top of* durable knowledge via
scenario and PRD-writing challenges.

- **Primary:** storage strength — long-term retention and reuse under pressure.
- **Secondary (deliberate, not deferred):** fluency — in-the-moment reasoning on
  novel scenarios, built on the durable base.
- **Deferred:** none. Fluency is not dropped; it is sequenced after durability.

---

## 2. Load-bearing principles

Each principle is committed as **policy** — violations are visible, not invisible
drift. Each has a concrete mechanism in the Telegram async channel.

### 2.1 Active recall / retrieval practice

The bot asks; the user retrieves from memory or fails. There is no passive reading
path that "counts" as learning.

- **Mechanism:** every daily unit ends in a challenge (recall / scenario / PRD /
  deep-dive). The lesson text is the *teach*; the challenge is the *retrieval*.
  The user answers async; the bot grades nightly.

### 2.2 Spaced repetition (SM-2)

Re-encounters are distributed over time, not massed. Each concept has an ease
factor and interval; wrong answers reset the interval, right answers lengthen it.

- **Mechanism:** SM-2 variant (Anki-style) per concept, owned by SQLite. The
  nightly grading job updates intervals and schedules the next due date. See
  [ADR-0002](docs/adr/0002-spaced-repetition.md) for the choice of SM-2 over
  alternatives.

### 2.3 Desirable difficulty — both arms explicit

Effortful retrieval builds storage strength; effortless retrieval does not. This
principle is the one most easily eroded by "helpful" defaults, so it is committed
as policy with two arms:

- **(a) Cold questions, no clue-leaking scaffolds.** The bot asks cold — no hint,
  no multiple-choice scaffold that leaks the answer, no "here's a reminder of
  yesterday's lesson" preamble before the challenge. Formatting must not leak
  clues (answer options of equal length/format where choices are used).
- **(b) Different-question re-asks are the *only* re-encounter mechanism.** When a
  concept is due or was missed, the strong model generates a *similar but
  different* challenge targeting the same concept. The bot **never** re-shows the
  same question — that tests recognition of a seen answer, not retrieval of the
  concept.

A "helpful" hint or a re-shown question is a **policy violation**, not a default.

### 2.4 Zone of proximal development (ZPD) — with the upward nudge

The bot challenges *just enough* — calibrated to observed performance, not a fixed
difficulty. Critically, ZPD has a *direction* the bare pass-rate mechanism does
not capture on its own: the bot must push the user *slightly above* their current
level, not just match it.

- **Mechanism:** questions tagged Easy / Medium / Hard; the bot tracks pass rate
  per tier (PLAN §4.1). The pass-rate calibration is the *instrument*; ZPD is the
  *policy* — the scheduler **nudges difficulty up** when the user is cruising
  (high pass rate at current tier), rather than optimizing for "you pass." A pure
  pass-rate optimizer could converge on "mostly Easy" — the opposite of ZPD. The
  destination sits above the user's current level; the coach climbs, it does not
  coast.

### 2.5 Mission-grounded / goal-anchored

Every learning unit traces to a gap in the ideal AI PM profile. No "AI news of the
day" filler. The mission fixes the scope of what is taught.

- **Mechanism:** every curriculum node carries a `gap` and `source` field
  (PLAN §4.2). Concepts without a gap mapping are rejected at curriculum time.

---

## 3. Deferred principles (not load-bearing)

These are sound ideas that are **not** committed as policy for Coach. They may
return later if the loop proves they're needed.

### 3.1 Interleaving — side-effect, not principle

The `teach` skill scopes interleaving to *skills practice only*. Coach's daily
format already interleaves by construction (1 PM concept + 1 AI concept + 1
rotating challenge), so the *perceived-variety* benefit is free. But interleaving
is **not** a scheduler commitment: if balancing across tracks ever conflicts with
SR due-dates, **SR timing wins**. Interleaving is a side-effect of the daily
format, not a load-bearing principle.

- **Cheap fallback if needed:** if three-in-a-row same-track re-asks feel stale,
  add a track-balance tiebreaker — a fix, not a principle.

### 3.2 Reference docs as compressed essence — gated on delivery surface

The `teach` skill treats reference docs (cheat sheets, glossaries) as first-class
artifacts. This is a *desired* principle for Coach, but whether Coach can honor it
depends on where such an artifact lives — which is the delivery-surface decision.

- **Status:** resolved by
  [Delivery surface: Telegram-only, or Telegram + a teach-style lesson repo?](https://github.com/msinghbehl/AI_PM_Learning_Bot/issues/3)
  — `reference/` is **deferred to Phase 2**. The principle is desired; its home is
  Phase 2's repo workspace, not Phase 1's loop.

---

## 4. Channel constraints (deferred by channel, not by choice)

Coach is a Telegram async chat loop, not a repo of HTML lessons with in-browser
quizzes. The following `teach`-skill mechanisms are **deferred by channel**, not
rejected on merit:

- **In-browser quizzes with auto-grading widgets** — no browser; grading is
  nightly via the strong model.
- **Interleaved in-lesson skill practice** — no lesson surface for interactive
  practice; "skills" (PRD writing, scenario reasoning) are trained via the
  rotating challenge format instead.
- **Lessons as beautiful HTML files** — Phase 1 pushes lesson text to Telegram and
  stages a markdown artifact to the repo (per #3); HTML rendering is a Phase 2
  concern.

---

## 5. Cross-references

- [ADR-0002 — Spaced repetition: SM-2 + storage-strength-primary](docs/adr/0002-spaced-repetition.md)
- [Delivery surface: Telegram-only, or Telegram + a teach-style lesson repo?](https://github.com/msinghbehl/AI_PM_Learning_Bot/issues/3) — resolves where durable artifacts live
- `PLAN.md` §2 (product principles), §4.1 (model routing & guardrails), §4.3 (daily loop), §4.4 (SR & self-improvement)
