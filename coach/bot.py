"""Coach Telegram bot — the single-process entrypoint.

Wires the deep modules (call_llm, cost_ledger, curriculum, grader, sr) into
python-telegram-bot handlers. Run with `python -m coach.bot`. All business logic
lives in the modules; this file only orchestrates.

Ported from Task_IQ's bot.py pattern: ApplicationBuilder + owner-only filter +
JobQueue run_daily for scheduled jobs.
"""
from __future__ import annotations

import datetime as dt
import logging
from datetime import date
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import (
    Application, ApplicationBuilder, CommandHandler, ContextTypes, filters,
)

import coach.config as config
from coach.call_llm import AnthropicClient, CallLLM
from coach.config import ChallengeType, GradeBand
from coach.cost_ledger import CostLedger
from coach.critic import Critic
from coach.curriculum import load_curriculum
from coach.grader import Grader
from coach.lesson import LessonGenerator
from coach.sr import initial_state, process_grade
from coach.store import Store

logging.basicConfig(
    format="%(asctime)s %(name)s %(levelname)s %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("coach")

TZ = ZoneInfo(config.TIMEZONE)


def _local_today() -> dt.date:
    return dt.datetime.now(TZ).date()


# --- Handlers ---


async def on_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Welcome the owner; reject silently handled by the owner-only filter."""
    await update.message.reply_text(
        "👋 Coach is ready. Commands:\n"
        "/today — get today's lesson\n"
        "/answer <text> — answer the current challenge\n"
        "/stats — see your progress\n"
        "/explain — re-read the lesson text\n"
        "/dispute <reasoning> — dispute a grade"
    )


def _format_lesson(lesson) -> str:
    """Format a Lesson for Telegram delivery."""
    return (
        f"📚 **Today's Lesson**\n\n"
        f"**PM Concept:** {lesson.pm_concept}\n\n"
        f"**AI Concept:** {lesson.ai_concept}\n\n"
        f"**Challenge ({lesson.challenge_type.value}):**\n{lesson.challenge}\n\n"
        f"_Answer with /answer <your answer>_"
    )


async def on_today(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Generate and send today's lesson on demand."""
    gen: LessonGenerator = context.bot_data["lesson_generator"]
    lesson = gen.generate()
    context.bot_data["current_lesson"] = lesson
    await update.message.reply_text(_format_lesson(lesson), parse_mode="Markdown")


async def on_push_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Scheduled 7am push job — generates and sends the daily lesson.

    Skip-if-asleep is handled by JobQueue: if the Mac is asleep at fire time,
    the job is skipped with no catch-up (run_daily default behavior).
    """
    gen: LessonGenerator = context.bot_data["lesson_generator"]
    store: Store = context.bot_data["store"]
    lesson = gen.generate()
    context.bot_data["current_lesson"] = lesson
    # Persist the challenge so /answer can reference it.
    import json as _json
    challenge_id = store.save_challenge(
        lesson.concept_node_id, lesson.challenge_type, lesson.challenge,
        _json.dumps({"pm_concept": lesson.pm_concept,
                    "ai_concept": lesson.ai_concept}),
        dt.datetime.now(TZ),
    )
    context.bot_data["current_challenge_id"] = challenge_id
    await context.bot.send_message(
        chat_id=config.owner_id(),
        text=_format_lesson(lesson),
        parse_mode="Markdown",
    )


async def on_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Store the user's answer against the current challenge."""
    store: Store = context.bot_data["store"]
    challenge = store.get_current_challenge()
    if challenge is None:
        await update.message.reply_text(
            "No active challenge. Use /today to get one."
        )
        return

    answer_text = " ".join(context.args) if context.args else ""
    if not answer_text:
        await update.message.reply_text(
            "Usage: /answer <your answer>"
        )
        return

    store.save_answer(challenge["id"], answer_text, dt.datetime.now(TZ))
    await update.message.reply_text(
        "✅ Answer recorded. I'll grade it tonight and you'll see the result "
        "in /stats tomorrow."
    )


async def on_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the user's progress — latest grades, SR state, and exit signals."""
    store: Store = context.bot_data["store"]
    from coach.exit_tracker import compute_signals

    today = _local_today()
    signals = compute_signals(store, today)

    lines = ["📊 **Progress**\n"]
    lines.append(f"Usage: {signals.usage_answered_days}/10 answered days "
                 f"(max {signals.usage_consecutive_misses} consecutive misses)")
    lines.append(f"SR: {signals.sr_re_asks} re-asks, "
                 f"{signals.sr_second_encounter_passes} second-encounter passes")
    if signals.fairness_pass is None:
        lines.append(f"Fairness: inconclusive ({signals.fairness_dispute_count} disputes)")
    else:
        lines.append(f"Fairness: {'pass' if signals.fairness_pass else 'fail'} "
                     f"({signals.fairness_dispute_count} disputes, "
                     f"{signals.fairness_grade_change_rate:.0%} grade-change)")

    if signals.kill_triggered:
        lines.append(f"\n⚠️ **KILL triggered**: {signals.kill_reason}")
    if signals.fix_and_extend:
        lines.append(f"\n🔧 Fix-and-extend: {signals.fix_and_extend_reason}")

    # Show latest grade if available
    challenge = store.get_current_challenge()
    if challenge and challenge.get("answered_at"):
        conn = store._conn
        row = conn.execute(
            "SELECT g.* FROM grades g JOIN answers a ON g.answer_id = a.id "
            "JOIN challenges c ON a.challenge_id = c.id "
            "WHERE c.id = ? AND g.is_deferred = 0 "
            "ORDER BY g.graded_at DESC LIMIT 1",
            (challenge["id"],),
        ).fetchone()
        if row:
            lines.append(f"\nLatest grade: {row['band']} (score {row['score']})")
            lines.append(f"Feedback: {row['feedback']}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def on_explain(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Re-surface the lesson text for the current concept."""
    lesson = context.bot_data.get("current_lesson")
    if lesson is None:
        await update.message.reply_text(
            "No lesson loaded. Use /today to get one."
        )
        return
    await update.message.reply_text(_format_lesson(lesson), parse_mode="Markdown")


async def on_grade_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Scheduled 11pm grade job — grades all ungraded answers via Sonnet.

    Per #6: the critic re-grades every answer. ≥1-band disagreement flags +
    defers (neither score writes to SR; interval held). On agreement, the grade
    writes to SR via SM-2.

    Skip-if-asleep is handled by JobQueue (same as the push job).
    """
    store: Store = context.bot_data["store"]
    grader: Grader = context.bot_data["grader"]
    critic: Critic = context.bot_data["critic"]
    ungraded = store.get_ungraded_answers()
    if not ungraded:
        return

    today = _local_today()

    for ans in ungraded:
        grade = grader.grade(
            challenge_text=ans["challenge_text"],
            challenge_type=ChallengeType(ans["challenge_type"]),
            answer_text=ans["answer_text"],
        )
        # Save the grader's grade
        grade_id = store.save_grade(
            answer_id=ans["id"],
            grader_model=grade.model,
            band=grade.band,
            score=grade.score,
            feedback=grade.feedback,
            rubric_id=grade.rubric_id,
            graded_at=dt.datetime.now(TZ),
        )

        # Critic re-grade
        review = critic.review(
            challenge_text=ans["challenge_text"],
            challenge_type=ChallengeType(ans["challenge_type"]),
            answer_text=ans["answer_text"],
            original_grade=grade,
        )

        if review.agrees:
            # Write to SR via SM-2
            _update_sr(store, ans["concept_node_id"], grade.band, today)
        else:
            # Flag + defer: mark the grade as deferred, hold the SR interval
            store.save_grade(
                answer_id=ans["id"],
                grader_model=review.critic_grade.model,
                band=review.critic_grade.band,
                score=review.critic_grade.score,
                feedback=review.critic_grade.feedback,
                rubric_id=review.critic_grade.rubric_id,
                graded_at=dt.datetime.now(TZ),
                is_critic=True,
                is_deferred=True,
            )
            log.info(
                "grade deferred for answer %d: grader=%s critic=%s delta=%d",
                ans["id"], grade.band.value, review.critic_grade.band.value,
                review.band_delta,
            )


def _update_sr(store: Store, concept_node_id: str, band: GradeBand, today) -> None:
    """Update SM-2 state for a concept after a resolved grade."""
    from coach.config import Difficulty
    from coach.sr import SRState
    raw = store.get_sr_state(concept_node_id)
    if raw is None:
        state = initial_state(Difficulty.MEDIUM, today)
    else:
        state = SRState(
            ease=raw["ease"],
            interval_days=raw["interval_days"],
            repetitions=raw["repetitions"],
            due_date=date.fromisoformat(raw["due_date"]),
            difficulty=Difficulty(raw["difficulty"]),
            last_grade_band=GradeBand(raw["last_grade_band"]) if raw["last_grade_band"] else None,
        )
    new_state = process_grade(state, band, today)
    store.upsert_sr_state(
        concept_node_id=concept_node_id,
        ease=new_state.ease,
        interval_days=new_state.interval_days,
        repetitions=new_state.repetitions,
        due_date=new_state.due_date,
        difficulty=new_state.difficulty,
        last_grade_band=new_state.last_grade_band.value if new_state.last_grade_band else None,
    )


async def on_dispute(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Dispute a grade — feeds reasoning as a claim to verify against the rubric.

    Per #6: one re-grade call, resolved score writes to SR, dispute logged.
    """
    store: Store = context.bot_data["store"]
    grader: Grader = context.bot_data["grader"]

    reasoning = " ".join(context.args) if context.args else ""
    if not reasoning:
        await update.message.reply_text("Usage: /dispute <your reasoning>")
        return

    # Find the most recent deferred grade for the latest answered challenge
    conn = store._conn
    row = conn.execute(
        "SELECT g.*, a.answer_text, c.challenge_text, c.challenge_type, "
        "c.concept_node_id FROM grades g "
        "JOIN answers a ON g.answer_id = a.id "
        "JOIN challenges c ON a.challenge_id = c.id "
        "WHERE g.is_deferred = 1 "
        "ORDER BY g.graded_at DESC LIMIT 1"
    ).fetchone()
    if row is None:
        await update.message.reply_text(
            "No disputed grades to resolve. Grades must be deferred first."
        )
        return

    # Re-grade with the dispute reasoning as additional context
    re_grade = grader.grade(
        challenge_text=row["challenge_text"],
        challenge_type=ChallengeType(row["challenge_type"]),
        answer_text=row["answer_text"] + "\n\nDispute reasoning: " + reasoning,
    )

    # Resolve: write the resolved score to SR
    _update_sr(store, row["concept_node_id"], re_grade.band, _local_today())

    # Save the resolved grade (not deferred)
    store.save_grade(
        answer_id=row["answer_id"],
        grader_model=re_grade.model,
        band=re_grade.band,
        score=re_grade.score,
        feedback=re_grade.feedback,
        rubric_id=re_grade.rubric_id,
        graded_at=dt.datetime.now(TZ),
    )

    # Log the dispute
    store.save_dispute(row["id"], reasoning, dt.datetime.now(TZ))

    await update.message.reply_text(
        f"⚖️ Dispute resolved. New grade: {re_grade.band.value} "
        f"(score {re_grade.score}). SR updated."
    )


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.error("handler error", exc_info=context.error)
    if isinstance(update, Update) and update.message:
        await update.message.reply_text(
            "⚠️ Something went wrong. It's logged; try again."
        )


async def _register_commands(app: Application) -> None:
    """Populate Telegram's '/' menu so commands are discoverable in-chat."""
    await app.bot.set_my_commands([
        ("today", "Get today's lesson"),
        ("answer", "Answer the current challenge"),
        ("stats", "See your progress"),
        ("explain", "Re-read the lesson text"),
        ("dispute", "Dispute a grade"),
    ])


def build_app() -> Application:
    """Build the Telegram Application with all handlers wired.

    Exposed as a function so tests can build a test app without running polling.
    """
    owner = config.validate()

    # Load curriculum and build the lesson generator.
    nodes = load_curriculum(config.CURRICULUM_PATH)
    ledger = CostLedger(config.DAILY_BUDGET_USD, config.WEEKLY_BUDGET_USD)
    client = AnthropicClient(config.ANTHROPIC_API_KEY)
    call_llm = CallLLM(client, ledger)
    generator = LessonGenerator(call_llm, nodes)
    store = Store.open(config.DATABASE_PATH)
    grader = Grader(call_llm, config.RUBRICS_DIR)
    critic = Critic(grader)

    app: Application = (
        ApplicationBuilder()
        .token(config.TELEGRAM_BOT_TOKEN)
        .post_init(_register_commands)
        .build()
    )
    app.bot_data["lesson_generator"] = generator
    app.bot_data["call_llm"] = call_llm
    app.bot_data["cost_ledger"] = ledger
    app.bot_data["store"] = store
    app.bot_data["grader"] = grader
    app.bot_data["critic"] = critic

    owner_only = filters.User(user_id=owner)

    app.add_handler(CommandHandler("start", on_start, filters=owner_only))
    app.add_handler(CommandHandler("today", on_today, filters=owner_only))
    app.add_handler(CommandHandler("answer", on_answer, filters=owner_only))
    app.add_handler(CommandHandler("stats", on_stats, filters=owner_only))
    app.add_handler(CommandHandler("explain", on_explain, filters=owner_only))
    app.add_handler(CommandHandler("dispute", on_dispute, filters=owner_only))
    app.add_error_handler(on_error)

    # 7am Pacific push job — skip-if-asleep (JobQueue default: no catch-up).
    app.job_queue.run_daily(
        on_push_job,
        time=dt.time(hour=config.PUSH_HOUR, tzinfo=TZ),
    )
    # 11pm Pacific grade job — skip-if-asleep.
    app.job_queue.run_daily(
        on_grade_job,
        time=dt.time(hour=config.GRADE_HOUR, tzinfo=TZ),
    )

    return app


def main() -> None:
    """Run the bot — single process, polling + JobQueue."""
    app = build_app()
    log.info(
        "Coach running — push at %02d:00, grade at %02d:00 %s",
        config.PUSH_HOUR, config.GRADE_HOUR, config.TIMEZONE,
    )
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
