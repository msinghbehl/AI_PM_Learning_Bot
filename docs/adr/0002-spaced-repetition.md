# ADR-0002 — Spaced repetition: SM-2 + storage-strength-primary

- **Status:** Accepted
- **Date:** 2026-07-25
- **Resolved by:** [Pedagogy model: which learning-science principles are load-bearing for Coach?](https://github.com/msinghbehl/AI_PM_Learning_Bot/issues/2)
- **Supersedes:** none
- **Related:** [PEDAGOGY.md](../../PEDAGOGY.md) (the full pedagogy model), [ADR-0001](./0001-delivery-surface.md) if present

## Context

`PLAN.md` §4.4 commits to an SM-2 variant (Anki-style) for spaced repetition, with
each concept carrying an ease factor and interval. The `teach` skill adds the
fluency-vs-storage-strength distinction: fluency is in-the-moment retrieval;
storage strength is long-term retention, and is the real goal. The pedagogy
decision (ticket #2) had to settle:

1. Whether storage strength or fluency is the primary goal of Coach's loop.
2. Whether SM-2 is the right SR algorithm given that goal.
3. The consequences of that choice for the scheduler and challenge formats.

This ADR records the SR-specific decision. The broader pedagogy model — including
ZPD, desirable difficulty, and the deferred principles — lives in
[PEDAGOGY.md](../../PEDAGOGY.md).

## Decision

**Storage strength is the primary goal; fluency is a deliberate secondary. SM-2
is the spaced-repetition algorithm.**

### Storage strength over fluency as primary

The destination is interview and on-the-job performance, which requires *durable*
retrieval first. Fluency (novel-scenario reasoning) is trained *on top of*
durable knowledge via scenario and PRD-writing challenges — it is sequenced after
durability, not dropped.

- **Considered:** fluency as primary (optimize for in-the-moment reasoning).
  **Rejected:** a coach that optimizes for "you can reason today" rather than
  "you can recall and reuse under interview pressure" drifts away from the
  destination.
- **Considered:** fluency deferred entirely. **Rejected:** this would gut the
  scenario/PRD formats that make Coach an *AI PM* coach rather than a flashcard
  app.

### SM-2 as the SR algorithm

SM-2 (Anki-style: per-concept ease factor + interval; wrong answers reset the
interval, right answers lengthen it) is the load-bearing mechanism for building
storage strength over time.

- **Considered:** a simpler fixed-interval schedule (e.g. review every N days).
  **Rejected:** does not adapt to per-concept difficulty; either over-reviews
  easy concepts (waste) or under-reviews hard ones (loss).
- **Considered:** a more complex algorithm (FSRS, half-life regression).
  **Rejected for Phase 1:** SM-2 is well-understood, cheap to implement, and
  sufficient for a single-user loop with ~20 concepts. The cost/quality
  architecture (PLAN §4.1) favors structure over sophistication; SR algorithm
  complexity is not the bottleneck. Can be revisited in Phase 2 if mastery data
  shows SM-2 mis-scheduling.

## Consequences

- **Positive:** the loop optimizes for the destination (durable recall under
  pressure). SM-2 is cheap, proven, and single-user-appropriate.
- **Positive:** fluency is not sacrificed — it is sequenced after durability via
  the scenario/PRD challenge formats.
- **Negative:** the scheduler must respect SM-2 intervals even when other
  principles (e.g. interleaving) would prefer a different ordering. Per
  PEDAGOGY.md §3.1, **SR timing wins** if interleaving conflicts.
- **Negative:** SM-2 does not natively encode the ZPD upward-nudge (PEDAGOGY.md
  §2.4). The scheduler must layer difficulty-tier adjustment *on top of* SM-2
  intervals — SM-2 decides *when* a concept is due; ZPD decides *how hard* the
  re-ask is.
- **Risk:** SM-2 may mis-schedule for a single user's actual retention curve.
  Mitigation: revisit in Phase 2 with mastery data; the SR state is in SQLite and
  is portable to a different algorithm if needed.

## Open questions for downstream tickets

- **Grading trust (#6):** SM-2 intervals are only as good as the grading that
  feeds them. If grading is unreliable, intervals drift. The grading-trust
  decision must de-risk this before the loop is trusted daily.
- **Curriculum source (#7):** SM-2 operates per-concept; the curriculum must be
  authored as discrete concepts with stable IDs for SR to attach to.
