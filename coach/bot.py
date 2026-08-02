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

    app: Application = (
        ApplicationBuilder()
        .token(config.TELEGRAM_BOT_TOKEN)
        .post_init(_register_commands)
        .build()
    )
    owner_only = filters.User(user_id=owner)

    app.add_handler(CommandHandler("start", on_start, filters=owner_only))
    app.add_error_handler(on_error)

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
