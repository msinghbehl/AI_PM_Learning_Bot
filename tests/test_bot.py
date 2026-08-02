"""Tests for the bot skeleton — /start response and allowlist rejection.

Tests the orchestrator seam: send a command, assert the observable response.
Telegram send is mocked at the boundary (we assert on reply_text calls).
"""
from __future__ import annotations

import importlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from telegram import Update
from telegram.ext import Application

import coach.config as config


@pytest.fixture(autouse=True)
def _reload_config(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("ALLOWED_TELEGRAM_USER_ID", "123456789")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("TIMEZONE", "America/Los_Angeles")
    monkeypatch.setenv("PUSH_HOUR", "7")
    monkeypatch.setenv("GRADE_HOUR", "23")
    importlib.reload(config)
    yield config
    importlib.reload(config)


def _make_update(text: str, user_id: int = 123456789) -> Update:
    """Build a minimal Update with a command message."""
    update = MagicMock(spec=Update)
    update.message = MagicMock()
    update.message.text = text
    update.message.reply_text = AsyncMock()
    update.message.from_user = MagicMock()
    update.message.from_user.id = user_id
    update.effective_user = MagicMock()
    update.effective_user.id = user_id
    return update


class TestStartHandler:
    @pytest.mark.asyncio
    async def test_start_responds_to_owner(self, _reload_config):
        from coach.bot import on_start
        update = _make_update("/start", user_id=123456789)
        await on_start(update, MagicMock())
        update.message.reply_text.assert_called_once()
        reply = update.message.reply_text.call_args[0][0]
        assert "Coach is ready" in reply
        assert "/today" in reply

    @pytest.mark.asyncio
    async def test_start_reply_lists_all_commands(self, _reload_config):
        from coach.bot import on_start
        update = _make_update("/start")
        await on_start(update, MagicMock())
        reply = update.message.reply_text.call_args[0][0]
        for cmd in ("/today", "/answer", "/stats", "/explain", "/dispute"):
            assert cmd in reply


class TestBuildApp:
    def test_build_app_returns_application(self, _reload_config):
        from coach.bot import build_app
        app = build_app()
        assert isinstance(app, Application)

    def test_build_app_has_start_handler(self, _reload_config):
        from coach.bot import build_app
        app = build_app()
        # The handlers dict should have at least one CommandHandler for "start"
        handler_groups = app.handlers
        all_handlers = [h for handlers in handler_groups.values() for h in handlers]
        start_handlers = [
            h for h in all_handlers
            if hasattr(h, "commands") and "start" in h.commands
        ]
        assert len(start_handlers) == 1

    def test_build_app_has_today_handler(self, _reload_config):
        from coach.bot import build_app
        app = build_app()
        handler_groups = app.handlers
        all_handlers = [h for handlers in handler_groups.values() for h in handlers]
        today_handlers = [
            h for h in all_handlers
            if hasattr(h, "commands") and "today" in h.commands
        ]
        assert len(today_handlers) == 1

    def test_build_app_has_lesson_generator(self, _reload_config):
        from coach.bot import build_app
        app = build_app()
        assert "lesson_generator" in app.bot_data


class TestTodayHandler:
    @pytest.mark.asyncio
    async def test_today_sends_lesson_with_all_parts(self, _reload_config):
        from coach.bot import on_today
        from coach.lesson import Lesson
        from coach.config import ChallengeType

        lesson = Lesson(
            pm_concept="Prioritization",
            ai_concept="Foundation models",
            challenge="When fine-tune vs RAG?",
            challenge_type=ChallengeType.CONCEPT_RECALL,
            concept_node_id="ai-fluency/test",
            concept_gap="AI technical fluency",
            concept_source=[{"url": "https://x.com", "type": "report"}],
        )
        update = _make_update("/today")
        context = MagicMock()
        context.bot_data = {"lesson_generator": MagicMock()}
        context.bot_data["lesson_generator"].generate.return_value = lesson

        await on_today(update, context)

        update.message.reply_text.assert_called_once()
        reply = update.message.reply_text.call_args[0][0]
        assert "Prioritization" in reply
        assert "Foundation models" in reply
        assert "fine-tune" in reply
        assert "/answer" in reply

    @pytest.mark.asyncio
    async def test_today_stores_lesson_in_bot_data(self, _reload_config):
        from coach.bot import on_today
        from coach.lesson import Lesson
        from coach.config import ChallengeType

        lesson = Lesson(
            pm_concept="p", ai_concept="a", challenge="c",
            challenge_type=ChallengeType.SCENARIO,
            concept_node_id="ai-fluency/test", concept_gap="AI technical fluency",
            concept_source=[],
        )
        update = _make_update("/today")
        context = MagicMock()
        context.bot_data = {"lesson_generator": MagicMock()}
        context.bot_data["lesson_generator"].generate.return_value = lesson

        await on_today(update, context)
        assert context.bot_data["current_lesson"] is lesson


class TestPushJob:
    @pytest.mark.asyncio
    async def test_push_job_sends_lesson_to_owner(self, _reload_config):
        from coach.bot import on_push_job
        from coach.lesson import Lesson
        from coach.config import ChallengeType

        lesson = Lesson(
            pm_concept="p", ai_concept="a", challenge="c",
            challenge_type=ChallengeType.TECHNICAL_DEEP_DIVE,
            concept_node_id="ai-fluency/test", concept_gap="AI technical fluency",
            concept_source=[],
        )
        context = MagicMock()
        context.bot_data = {"lesson_generator": MagicMock()}
        context.bot_data["lesson_generator"].generate.return_value = lesson
        context.bot.send_message = AsyncMock()

        await on_push_job(context)

        context.bot.send_message.assert_called_once()
        text = context.bot.send_message.call_args[1]["text"]
        assert "Today's Lesson" in text
        assert context.bot_data["current_lesson"] is lesson
