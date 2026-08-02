"""Central configuration for the Coach bot.

Loads `.env`, exposes every setting and the fixed enums the bot enforces, and
validates that required secrets are present. Import this module anywhere that
needs config; call `validate()` once at startup to fail fast with a clear message.

Ported from Task_IQ's config.py pattern (enum enforcement + fail-fast validation).
"""
from __future__ import annotations

import os
from enum import Enum
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the project root (the directory this file's parent lives in).
_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")


# --- Secrets & settings (from environment) ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
ALLOWED_TELEGRAM_USER_ID = os.getenv("ALLOWED_TELEGRAM_USER_ID", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_REPO = os.getenv("GITHUB_REPO", "msinghbehl/AI_PM_Learning_Bot")

# Scheduling (Pacific, per #9)
TIMEZONE = os.getenv("TIMEZONE", "America/Los_Angeles")
PUSH_HOUR = int(os.getenv("PUSH_HOUR", "7"))
GRADE_HOUR = int(os.getenv("GRADE_HOUR", "23"))

# Cost caps (per #5 fallback ladder)
DAILY_BUDGET_USD = float(os.getenv("DAILY_BUDGET_USD", "0.65"))
WEEKLY_BUDGET_USD = float(os.getenv("WEEKLY_BUDGET_USD", "5.00"))

# Curriculum path (relative to repo root)
CURRICULUM_PATH = _ROOT / "curriculum" / "ai-technical-fluency.yaml"
RUBRICS_DIR = _ROOT / "rubrics"
DATABASE_PATH = _ROOT / "data" / "coach.db"
LESSONS_STAGING_BRANCH = "lessons-staging"


class ModelName(str, Enum):
    """The three model tiers behind the provider-agnostic call_llm wrapper."""

    HAIKU = "claude-haiku-4-5"      # cheap / generate
    SONNET = "claude-sonnet-4-6"    # strong / grade + critic
    OPUS = "claude-opus-4-5"        # per-call escalation


class ChallengeType(str, Enum):
    """The three rotating challenge formats for Phase 1."""

    CONCEPT_RECALL = "concept-recall"
    SCENARIO = "scenario"
    TECHNICAL_DEEP_DIVE = "technical-deep-dive"


class Difficulty(str, Enum):
    """ZPD difficulty tiers — scheduler nudges up when cruising."""

    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class GradeBand(str, Enum):
    """Rubric scale labels (shared skeleton, per #6)."""

    BELOW = "below"      # 0 — does not meet
    APPROACHING = "approaching"  # 1 — partial
    MEETS = "meets"      # 2 — meets the bar
    EXCEEDS = "exceeds"  # 3 — exceeds


# --- Validation ---
_REQUIRED = (
    "TELEGRAM_BOT_TOKEN",
    "ALLOWED_TELEGRAM_USER_ID",
    "ANTHROPIC_API_KEY",
)


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or malformed."""


def owner_id() -> int:
    """Return the owner's Telegram user id as an int (raises ConfigError if unset/bad)."""
    try:
        return int(ALLOWED_TELEGRAM_USER_ID)
    except (TypeError, ValueError) as exc:
        raise ConfigError(
            "ALLOWED_TELEGRAM_USER_ID must be your numeric Telegram user id "
            "(get it from @userinfobot)."
        ) from exc


def validate() -> int:
    """Fail fast if required config is missing. Returns the owner's Telegram id.

    Call this at startup. It names exactly what is missing so setup is painless.
    """
    missing = [name for name in _REQUIRED if not globals().get(name)]
    if missing:
        raise ConfigError(
            "Missing required values in .env: "
            + ", ".join(missing)
            + ".\nCopy .env.example to .env and fill them in."
        )
    return owner_id()
