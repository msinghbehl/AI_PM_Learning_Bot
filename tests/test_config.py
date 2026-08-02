"""Tests for the config module — enum enforcement and fail-fast validation."""
from __future__ import annotations

import importlib
import os

import pytest


@pytest.fixture(autouse=True)
def _reload_config(monkeypatch):
    """Reload config with test env vars so module state is deterministic."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("ALLOWED_TELEGRAM_USER_ID", "123456789")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp-test")
    monkeypatch.setenv("TIMEZONE", "America/Los_Angeles")
    monkeypatch.setenv("PUSH_HOUR", "7")
    monkeypatch.setenv("GRADE_HOUR", "23")
    monkeypatch.setenv("DAILY_BUDGET_USD", "0.65")
    monkeypatch.setenv("WEEKLY_BUDGET_USD", "5.00")
    import coach.config as config
    importlib.reload(config)
    yield config
    importlib.reload(config)


class TestEnums:
    def test_model_name_has_three_tiers(self, _reload_config):
        config = _reload_config
        assert config.ModelName.HAIKU.value == "claude-haiku-4-5"
        assert config.ModelName.SONNET.value == "claude-sonnet-4-6"
        assert config.ModelName.OPUS.value == "claude-opus-4-5"

    def test_challenge_type_has_three_formats(self, _reload_config):
        config = _reload_config
        types = {ct.value for ct in config.ChallengeType}
        assert types == {"concept-recall", "scenario", "technical-deep-dive"}

    def test_difficulty_has_three_tiers(self, _reload_config):
        config = _reload_config
        assert {d.value for d in config.Difficulty} == {
            "easy", "medium", "hard"}

    def test_grade_band_has_four_levels(self, _reload_config):
        config = _reload_config
        assert {g.value for g in config.GradeBand} == {
            "below", "approaching", "meets", "exceeds"}


class TestValidate:
    def test_returns_owner_id_when_all_present(self, _reload_config):
        config = _reload_config
        assert config.validate() == 123456789

    def test_fails_fast_on_missing_telegram_token(self, _reload_config, monkeypatch):
        config = _reload_config
        monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "")
        with pytest.raises(config.ConfigError, match="TELEGRAM_BOT_TOKEN"):
            config.validate()

    def test_fails_fast_on_missing_anthropic_key(self, _reload_config, monkeypatch):
        config = _reload_config
        monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "")
        with pytest.raises(config.ConfigError, match="ANTHROPIC_API_KEY"):
            config.validate()

    def test_fails_fast_on_bad_owner_id(self, _reload_config, monkeypatch):
        config = _reload_config
        monkeypatch.setattr(config, "ALLOWED_TELEGRAM_USER_ID", "not-a-number")
        with pytest.raises(config.ConfigError, match="numeric Telegram user id"):
            config.owner_id()
