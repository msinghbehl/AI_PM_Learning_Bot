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
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import (
    Application, ApplicationBuilder, CommandHandler, ContextTypes, filters,
)

import coach.config as config
from coach.call_llm import AnthropicClient, CallLLM
from coach.cost_ledger import CostLedger
from coach.curriculum import load_curriculum
from coach.lesson import LessonGenerator

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
    lesson = gen.generate()
    context.bot_data["current_lesson"] = lesson
    await context.bot.send_message(
        chat_id=config.owner_id(),
        text=_format_lesson(lesson),
        parse_mode="Markdown",
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

    app: Application = (
        ApplicationBuilder()
        .token(config.TELEGRAM_BOT_TOKEN)
        .post_init(_register_commands)
        .build()
    )
    app.bot_data["lesson_generator"] = generator
    app.bot_data["call_llm"] = call_llm
    app.bot_data["cost_ledger"] = ledger

    owner_only = filters.User(user_id=owner)

    app.add_handler(CommandHandler("start", on_start, filters=owner_only))
    app.add_handler(CommandHandler("today", on_today, filters=owner_only))
    app.add_error_handler(on_error)

    # 7am Pacific push job — skip-if-asleep (JobQueue default: no catch-up).
    app.job_queue.run_daily(
        on_push_job,
        time=dt.time(hour=config.PUSH_HOUR, tzinfo=TZ),
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
