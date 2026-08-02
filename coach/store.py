"""SQLite store — owns SR state, challenge history, grades, cost ledger.

Per #32 Phase 3: raw schema, no ORM. The store is the single source of truth for
all bot state. Tests use a tmp_path database; production uses data/coach.db.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Any

from coach.config import ChallengeType, Difficulty, GradeBand, ModelName


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: Path) -> sqlite3.Connection:
    """Create the schema if it doesn't exist. Returns a connection."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = _connect(db_path)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS challenges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            concept_node_id TEXT NOT NULL,
            challenge_type TEXT NOT NULL,
            challenge_text TEXT NOT NULL,
            lesson_json TEXT NOT NULL,
            pushed_at TEXT NOT NULL,
            answered_at TEXT
        );

        CREATE TABLE IF NOT EXISTS answers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            challenge_id INTEGER NOT NULL REFERENCES challenges(id),
            answer_text TEXT NOT NULL,
            answered_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS grades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            answer_id INTEGER NOT NULL REFERENCES answers(id),
            grader_model TEXT NOT NULL,
            band TEXT NOT NULL,
            score INTEGER NOT NULL,
            feedback TEXT NOT NULL,
            rubric_id TEXT NOT NULL,
            graded_at TEXT NOT NULL,
            is_critic INTEGER NOT NULL DEFAULT 0,
            is_disputed INTEGER NOT NULL DEFAULT 0,
            is_deferred INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS sr_state (
            concept_node_id TEXT PRIMARY KEY,
            ease REAL NOT NULL DEFAULT 2.5,
            interval_days INTEGER NOT NULL DEFAULT 0,
            repetitions INTEGER NOT NULL DEFAULT 0,
            due_date TEXT NOT NULL,
            difficulty TEXT NOT NULL DEFAULT 'medium',
            last_grade_band TEXT
        );

        CREATE TABLE IF NOT EXISTS cost_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            model TEXT NOT NULL,
            input_tokens INTEGER NOT NULL,
            output_tokens INTEGER NOT NULL,
            cache_read_tokens INTEGER NOT NULL DEFAULT 0,
            cost_usd REAL NOT NULL,
            purpose TEXT NOT NULL,
            logged_at TEXT NOT NULL,
            day TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS disputes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            grade_id INTEGER NOT NULL REFERENCES grades(id),
            reasoning TEXT NOT NULL,
            resolved_band TEXT,
            resolved_at TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """
    )
    conn.commit()
    return conn


class Store:
    """SQLite-backed store for all bot state."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    @classmethod
    def open(cls, db_path: Path) -> "Store":
        return cls(init_db(db_path))

    def close(self) -> None:
        self._conn.close()

    # --- challenges ---

    def save_challenge(
        self,
        concept_node_id: str,
        challenge_type: ChallengeType,
        challenge_text: str,
        lesson_json: str,
        pushed_at: datetime,
    ) -> int:
        cur = self._conn.execute(
            "INSERT INTO challenges (concept_node_id, challenge_type, challenge_text, "
            "lesson_json, pushed_at) VALUES (?, ?, ?, ?, ?)",
            (concept_node_id, challenge_type.value, challenge_text, lesson_json,
             pushed_at.isoformat()),
        )
        self._conn.commit()
        return cur.lastrowid

    def get_challenge(self, challenge_id: int) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM challenges WHERE id = ?", (challenge_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_current_challenge(self) -> dict[str, Any] | None:
        """Return the most recent unanswered challenge."""
        row = self._conn.execute(
            "SELECT * FROM challenges WHERE answered_at IS NULL "
            "ORDER BY pushed_at DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None

    def mark_answered(self, challenge_id: int, answered_at: datetime) -> None:
        self._conn.execute(
            "UPDATE challenges SET answered_at = ? WHERE id = ?",
            (answered_at.isoformat(), challenge_id),
        )
        self._conn.commit()

    # --- answers ---

    def save_answer(
        self, challenge_id: int, answer_text: str, answered_at: datetime
    ) -> int:
        cur = self._conn.execute(
            "INSERT INTO answers (challenge_id, answer_text, answered_at) "
            "VALUES (?, ?, ?)",
            (challenge_id, answer_text, answered_at.isoformat()),
        )
        self.mark_answered(challenge_id, answered_at)
        self._conn.commit()
        return cur.lastrowid

    def get_answer(self, answer_id: int) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM answers WHERE id = ?", (answer_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_ungraded_answers(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT a.*, c.challenge_text, c.challenge_type, c.concept_node_id, "
            "c.lesson_json FROM answers a "
            "JOIN challenges c ON a.challenge_id = c.id "
            "WHERE a.id NOT IN (SELECT answer_id FROM grades) "
            "ORDER BY a.answered_at"
        ).fetchall()
        return [dict(r) for r in rows]

    # --- grades ---

    def save_grade(
        self,
        answer_id: int,
        grader_model: ModelName,
        band: GradeBand,
        score: int,
        feedback: str,
        rubric_id: str,
        graded_at: datetime,
        is_critic: bool = False,
        is_deferred: bool = False,
    ) -> int:
        cur = self._conn.execute(
            "INSERT INTO grades (answer_id, grader_model, band, score, feedback, "
            "rubric_id, graded_at, is_critic, is_disputed, is_deferred) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?)",
            (answer_id, grader_model.value, band.value, score, feedback, rubric_id,
             graded_at.isoformat(), int(is_critic), int(is_deferred)),
        )
        self._conn.commit()
        return cur.lastrowid

    def get_grades_for_answer(self, answer_id: int) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM grades WHERE answer_id = ?", (answer_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_latest_grade(self, answer_id: int) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM grades WHERE answer_id = ? AND is_deferred = 0 "
            "ORDER BY graded_at DESC LIMIT 1",
            (answer_id,),
        ).fetchone()
        return dict(row) if row else None

    # --- SR state ---

    def get_sr_state(self, concept_node_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM sr_state WHERE concept_node_id = ?",
            (concept_node_id,),
        ).fetchone()
        return dict(row) if row else None

    def upsert_sr_state(
        self,
        concept_node_id: str,
        ease: float,
        interval_days: int,
        repetitions: int,
        due_date: date,
        difficulty: Difficulty,
        last_grade_band: str | None = None,
    ) -> None:
        self._conn.execute(
            "INSERT INTO sr_state (concept_node_id, ease, interval_days, "
            "repetitions, due_date, difficulty, last_grade_band) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(concept_node_id) DO UPDATE SET "
            "ease=excluded.ease, interval_days=excluded.interval_days, "
            "repetitions=excluded.repetitions, due_date=excluded.due_date, "
            "difficulty=excluded.difficulty, last_grade_band=excluded.last_grade_band",
            (concept_node_id, ease, interval_days, repetitions,
             due_date.isoformat(), difficulty.value, last_grade_band),
        )
        self._conn.commit()

    # --- meta ---

    def get_meta(self, key: str) -> str | None:
        row = self._conn.execute(
            "SELECT value FROM meta WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else None

    def set_meta(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        self._conn.commit()

    # --- disputes ---

    def save_dispute(
        self, grade_id: int, reasoning: str, created_at: datetime
    ) -> int:
        cur = self._conn.execute(
            "INSERT INTO disputes (grade_id, reasoning, created_at) "
            "VALUES (?, ?, ?)",
            (grade_id, reasoning, created_at.isoformat()),
        )
        self._conn.commit()
        return cur.lastrowid

    def resolve_dispute(
        self, dispute_id: int, resolved_band: GradeBand, resolved_at: datetime
    ) -> None:
        self._conn.execute(
            "UPDATE disputes SET resolved_band = ?, resolved_at = ? WHERE id = ?",
            (resolved_band.value, resolved_at.isoformat(), dispute_id),
        )
        self._conn.commit()
