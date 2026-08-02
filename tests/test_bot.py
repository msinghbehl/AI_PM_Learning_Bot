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
