"""Tests for the bot skeleton — /start response and allowlist rejection.

Tests the orchestrator seam: send a command, assert the observable response.
Telegram send is mocked at the boundary (we assert on reply_text calls).
"""
from __future__ import annotations

import importlib
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from telegram import Update
from telegram.ext import Application

import coach.config as config
from coach.config import ChallengeType


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
        all_handlers = [h for handlers in handler_groups.values()
                        for h in handlers]
        start_handlers = [
            h for h in all_handlers
            if hasattr(h, "commands") and "start" in h.commands
        ]
        assert len(start_handlers) == 1

    def test_build_app_has_today_handler(self, _reload_config):
        from coach.bot import build_app
        app = build_app()
        handler_groups = app.handlers
        all_handlers = [h for handlers in handler_groups.values()
                        for h in handlers]
        today_handlers = [
            h for h in all_handlers
            if hasattr(h, "commands") and "today" in h.commands
        ]
        assert len(today_handlers) == 1

    def test_build_app_has_lesson_generator(self, _reload_config):
        from coach.bot import build_app
        app = build_app()
        assert "lesson_generator" in app.bot_data

    def test_build_app_job_queue_is_not_none(self, _reload_config):
        """JobQueue must be available (requires [job-queue] extra)."""
        from coach.bot import build_app
        app = build_app()
        assert app.job_queue is not None

    def test_main_does_not_raise_no_event_loop(self, _reload_config):
        """main() must not raise 'no current event loop' on Python 3.14+.

        Python 3.14 removed implicit event loop creation. PTB 21.x calls
        asyncio.get_event_loop() which raises RuntimeError. PTB 22.x fixed
        this. This test mocks run_polling to avoid blocking, but verifies
        the async runtime initializes without the event loop error.
        """
        from coach.bot import main
        with patch("coach.bot.Application.run_polling") as mock_run:
            main()
            mock_run.assert_called_once()


class TestTodayHandler:
    @pytest.mark.asyncio
    async def test_today_sends_lesson_with_all_parts(self, _reload_config, tmp_path):
        from coach.bot import on_today
        from coach.lesson import Lesson
        from coach.store import Store, init_db

        lesson = Lesson(
            pm_concept="Prioritization",
            ai_concept="Foundation models",
            challenge="When fine-tune vs RAG?",
            challenge_type=ChallengeType.CONCEPT_RECALL,
            concept_node_id="ai-fluency/test",
            concept_gap="AI technical fluency",
            concept_source=[{"url": "https://x.com", "type": "report"}],
        )
        store = Store(init_db(tmp_path / "test.db"))
        update = _make_update("/today")
        context = MagicMock()
        context.bot_data = {"lesson_generator": MagicMock(), "store": store}
        context.bot_data["lesson_generator"].generate.return_value = lesson

        await on_today(update, context)

        update.message.reply_text.assert_called_once()
        reply = update.message.reply_text.call_args[0][0]
        assert "Prioritization" in reply
        assert "Foundation models" in reply
        assert "fine-tune" in reply
        assert "/answer" in reply

    @pytest.mark.asyncio
    async def test_today_stores_lesson_in_bot_data(self, _reload_config, tmp_path):
        from coach.bot import on_today
        from coach.lesson import Lesson
        from coach.store import Store, init_db

        lesson = Lesson(
            pm_concept="p", ai_concept="a", challenge="c",
            challenge_type=ChallengeType.SCENARIO,
            concept_node_id="ai-fluency/test", concept_gap="AI technical fluency",
            concept_source=[],
        )
        store = Store(init_db(tmp_path / "test.db"))
        update = _make_update("/today")
        context = MagicMock()
        context.bot_data = {"lesson_generator": MagicMock(), "store": store}
        context.bot_data["lesson_generator"].generate.return_value = lesson

        await on_today(update, context)
        assert context.bot_data["current_lesson"] is lesson


class TestPushJob:
    @pytest.mark.asyncio
    async def test_push_job_sends_lesson_to_owner(self, _reload_config, tmp_path):
        from coach.bot import on_push_job
        from coach.lesson import Lesson
        from coach.store import Store, init_db

        lesson = Lesson(
            pm_concept="p", ai_concept="a", challenge="c",
            challenge_type=ChallengeType.TECHNICAL_DEEP_DIVE,
            concept_node_id="ai-fluency/test", concept_gap="AI technical fluency",
            concept_source=[],
        )
        store = Store(init_db(tmp_path / "test.db"))
        context = MagicMock()
        context.bot_data = {"lesson_generator": MagicMock(), "store": store}
        context.bot_data["lesson_generator"].generate.return_value = lesson
        context.bot.send_message = AsyncMock()

        await on_push_job(context)

        context.bot.send_message.assert_called_once()
        text = context.bot.send_message.call_args[1]["text"]
        assert "Today's Lesson" in text
        assert context.bot_data["current_lesson"] is lesson

    @pytest.mark.asyncio
    async def test_push_job_includes_yesterday_grade_when_available(
        self, _reload_config, tmp_path
    ):
        """7am push sends grade result as a separate message before the lesson (#42)."""
        from coach.bot import on_push_job
        from coach.lesson import Lesson
        from coach.store import Store, init_db
        from coach.config import GradeBand, ModelName

        store = Store(init_db(tmp_path / "test.db"))
        # Yesterday's challenge, answered, graded
        cid = store.save_challenge("a", ChallengeType.SCENARIO, "q1", "{}",
                                    datetime(2026, 8, 1, 7))
        aid = store.save_answer(cid, "ans", datetime(2026, 8, 1, 12))
        store.save_grade(aid, ModelName.SONNET, GradeBand.MEETS, 2,
                         "Good understanding of RAG tradeoffs",
                         "scenario", datetime(2026, 8, 1, 23))

        lesson = Lesson(
            pm_concept="p", ai_concept="a", challenge="c",
            challenge_type=ChallengeType.TECHNICAL_DEEP_DIVE,
            concept_node_id="ai-fluency/test", concept_gap="AI technical fluency",
            concept_source=[],
        )
        context = MagicMock()
        context.bot_data = {"lesson_generator": MagicMock(), "store": store}
        context.bot_data["lesson_generator"].generate.return_value = lesson
        context.bot.send_message = AsyncMock()

        await on_push_job(context)

        # Two messages: grade result + lesson
        assert context.bot.send_message.call_count == 2
        grade_text = context.bot.send_message.call_args_list[0][1]["text"]
        lesson_text = context.bot.send_message.call_args_list[1][1]["text"]
        assert "Result from" in grade_text
        assert "meets" in grade_text.lower() or "Good understanding" in grade_text
        assert "Today's Lesson" in lesson_text

    @pytest.mark.asyncio
    async def test_push_job_no_grade_message_when_no_prior_grade(
        self, _reload_config, tmp_path
    ):
        """7am push sends only the lesson when no prior grade exists (#42)."""
        from coach.bot import on_push_job
        from coach.lesson import Lesson
        from coach.store import Store, init_db

        store = Store(init_db(tmp_path / "test.db"))
        lesson = Lesson(
            pm_concept="p", ai_concept="a", challenge="c",
            challenge_type=ChallengeType.TECHNICAL_DEEP_DIVE,
            concept_node_id="ai-fluency/test", concept_gap="AI technical fluency",
            concept_source=[],
        )
        context = MagicMock()
        context.bot_data = {"lesson_generator": MagicMock(), "store": store}
        context.bot_data["lesson_generator"].generate.return_value = lesson
        context.bot.send_message = AsyncMock()

        await on_push_job(context)

        # Only the lesson message, no grade message
        assert context.bot.send_message.call_count == 1
        text = context.bot.send_message.call_args[1]["text"]
        assert "Today's Lesson" in text
        assert "Result from" not in text


class TestStatsHandler:
    @pytest.mark.asyncio
    async def test_stats_shows_latest_grade_when_one_exists(
        self, _reload_config, tmp_path
    ):
        """/stats shows the most recent grade + feedback across all challenges (#41)."""
        from coach.bot import on_stats
        from coach.store import Store, init_db
        from coach.config import GradeBand, ModelName

        store = Store(init_db(tmp_path / "test.db"))
        # Day 1 challenge, answered, graded
        cid1 = store.save_challenge("a", ChallengeType.SCENARIO, "q1", "{}",
                                    datetime(2026, 8, 1, 7))
        aid1 = store.save_answer(cid1, "ans1", datetime(2026, 8, 1, 12))
        store.save_grade(aid1, ModelName.SONNET, GradeBand.MEETS, 2,
                         "Good grasp of RAG fundamentals",
                         "scenario", datetime(2026, 8, 1, 23))
        # Day 2 challenge, answered, NOT yet graded (current)
        cid2 = store.save_challenge("b", ChallengeType.CONCEPT_RECALL, "q2", "{}",
                                    datetime(2026, 8, 2, 7))
        store.save_answer(cid2, "ans2", datetime(2026, 8, 2, 12))

        update = _make_update("/stats")
        context = MagicMock()
        context.bot_data = {"store": store}

        await on_stats(update, context)

        reply = update.message.reply_text.call_args[0][0]
        assert "meets" in reply.lower() or "Good grasp" in reply

    @pytest.mark.asyncio
    async def test_stats_no_grade_line_when_no_grades(
        self, _reload_config, tmp_path
    ):
        """/stats doesn't show a grade section when no grades exist yet (#41)."""
        from coach.bot import on_stats
        from coach.store import Store, init_db

        store = Store(init_db(tmp_path / "test.db"))
        update = _make_update("/stats")
        context = MagicMock()
        context.bot_data = {"store": store}

        await on_stats(update, context)

        reply = update.message.reply_text.call_args[0][0]
        assert "Latest grade" not in reply
        assert "Feedback" not in reply


class TestAnswerHandler:
    @pytest.mark.asyncio
    async def test_answer_stores_answer_for_current_challenge(self, _reload_config, tmp_path):
        from coach.bot import on_answer
        from coach.store import Store, init_db

        store = Store(init_db(tmp_path / "test.db"))
        cid = store.save_challenge("a", ChallengeType.CONCEPT_RECALL, "q", "{}",
                                   datetime(2026, 8, 1, 7))

        update = _make_update("/answer my response")
        context = MagicMock()
        context.bot_data = {"store": store}
        context.args = ["my", "response"]

        await on_answer(update, context)

        update.message.reply_text.assert_called_once()
        reply = update.message.reply_text.call_args[0][0]
        assert "recorded" in reply.lower()
        ch = store.get_challenge(cid)
        assert ch["answered_at"] is not None

    @pytest.mark.asyncio
    async def test_answer_no_active_challenge(self, _reload_config, tmp_path):
        from coach.bot import on_answer
        from coach.store import Store, init_db

        store = Store(init_db(tmp_path / "test.db"))
        update = _make_update("/answer something")
        context = MagicMock()
        context.bot_data = {"store": store}
        context.args = ["something"]

        await on_answer(update, context)
        reply = update.message.reply_text.call_args[0][0]
        assert "No active challenge" in reply

    @pytest.mark.asyncio
    async def test_answer_empty_text(self, _reload_config, tmp_path):
        from coach.bot import on_answer
        from coach.store import Store, init_db

        store = Store(init_db(tmp_path / "test.db"))
        store.save_challenge("a", ChallengeType.CONCEPT_RECALL, "q", "{}",
                             datetime(2026, 8, 1, 7))
        update = _make_update("/answer")
        context = MagicMock()
        context.bot_data = {"store": store}
        context.args = []

        await on_answer(update, context)
        reply = update.message.reply_text.call_args[0][0]
        assert "Usage" in reply


class TestExplainHandler:
    @pytest.mark.asyncio
    async def test_explain_resurfaces_lesson(self, _reload_config):
        from coach.bot import on_explain
        from coach.lesson import Lesson

        lesson = Lesson(
            pm_concept="p", ai_concept="a", challenge="c",
            challenge_type=ChallengeType.SCENARIO,
            concept_node_id="ai-fluency/test", concept_gap="AI technical fluency",
            concept_source=[],
        )
        update = _make_update("/explain")
        context = MagicMock()
        context.bot_data = {"current_lesson": lesson}

        await on_explain(update, context)
        update.message.reply_text.assert_called_once()
        reply = update.message.reply_text.call_args[0][0]
        assert "Today's Lesson" in reply

    @pytest.mark.asyncio
    async def test_explain_no_lesson(self, _reload_config):
        from coach.bot import on_explain

        update = _make_update("/explain")
        context = MagicMock()
        context.bot_data = {}

        await on_explain(update, context)
        reply = update.message.reply_text.call_args[0][0]
        assert "No lesson" in reply


class TestGradeJob:
    @pytest.mark.asyncio
    async def test_grade_job_grades_ungraded_answers(self, _reload_config, tmp_path):
        from coach.bot import on_grade_job
        from coach.store import Store, init_db
        from coach.config import GradeBand, ModelName

        store = Store(init_db(tmp_path / "test.db"))
        cid = store.save_challenge("a", ChallengeType.CONCEPT_RECALL, "What is RAG?", "{}",
                                   datetime(2026, 8, 1, 7))
        aid = store.save_answer(
            cid, "RAG retrieves chunks", datetime(2026, 8, 1, 12))

        grader = MagicMock()
        grader.grade.return_value = MagicMock(
            band=GradeBand.MEETS, score=2, feedback="good",
            rubric_id="concept-recall", model=ModelName.SONNET,
        )

        context = MagicMock()
        context.bot_data = {"store": store,
                            "grader": grader, "critic": MagicMock()}

        await on_grade_job(context)

        grader.grade.assert_called_once()
        grades = store.get_grades_for_answer(aid)
        assert len(grades) == 1
        assert grades[0]["band"] == "meets"

    @pytest.mark.asyncio
    async def test_grade_job_no_ungraded_does_nothing(self, _reload_config, tmp_path):
        from coach.bot import on_grade_job
        from coach.store import Store, init_db

        store = Store(init_db(tmp_path / "test.db"))
        grader = MagicMock()
        context = MagicMock()
        context.bot_data = {"store": store,
                            "grader": grader, "critic": MagicMock()}

        await on_grade_job(context)
        grader.grade.assert_not_called()


class TestCriticIntegration:
    @pytest.mark.asyncio
    async def test_grade_job_defers_on_critic_disagreement(self, _reload_config, tmp_path):
        from coach.bot import on_grade_job
        from coach.store import Store, init_db
        from coach.config import GradeBand, ModelName
        from coach.critic import CriticResult

        store = Store(init_db(tmp_path / "test.db"))
        cid = store.save_challenge("a", ChallengeType.CONCEPT_RECALL, "q", "{}",
                                   datetime(2026, 8, 1, 7))
        aid = store.save_answer(cid, "ans", datetime(2026, 8, 1, 12))

        grader = MagicMock()
        grader.grade.return_value = MagicMock(
            band=GradeBand.MEETS, score=2, feedback="good",
            rubric_id="concept-recall", model=ModelName.SONNET,
        )
        critic = MagicMock()
        critic.review.return_value = CriticResult(
            critic_grade=MagicMock(
                band=GradeBand.BELOW, score=0, feedback="bad",
                rubric_id="concept-recall", model=ModelName.SONNET,
            ),
            agrees=False, band_delta=2,
        )

        context = MagicMock()
        context.bot_data = {"store": store, "grader": grader, "critic": critic}

        await on_grade_job(context)

        grades = store.get_grades_for_answer(aid)
        assert len(grades) == 2  # grader + critic
        # The critic grade should be deferred
        deferred = [g for g in grades if g["is_deferred"]]
        assert len(deferred) == 1
        # SR state should NOT be written (interval held)
        assert store.get_sr_state("a") is None

    @pytest.mark.asyncio
    async def test_grade_job_writes_sr_on_agreement(self, _reload_config, tmp_path):
        from coach.bot import on_grade_job
        from coach.store import Store, init_db
        from coach.config import GradeBand, ModelName
        from coach.critic import CriticResult

        store = Store(init_db(tmp_path / "test.db"))
        cid = store.save_challenge("a", ChallengeType.CONCEPT_RECALL, "q", "{}",
                                   datetime(2026, 8, 1, 7))
        aid = store.save_answer(cid, "ans", datetime(2026, 8, 1, 12))

        grader = MagicMock()
        grader.grade.return_value = MagicMock(
            band=GradeBand.MEETS, score=2, feedback="good",
            rubric_id="concept-recall", model=ModelName.SONNET,
        )
        critic = MagicMock()
        critic.review.return_value = CriticResult(
            critic_grade=MagicMock(
                band=GradeBand.MEETS, score=2, feedback="agree",
                rubric_id="concept-recall", model=ModelName.SONNET,
            ),
            agrees=True, band_delta=0,
        )

        context = MagicMock()
        context.bot_data = {"store": store, "grader": grader, "critic": critic}

        await on_grade_job(context)

        # SR state should be written
        sr = store.get_sr_state("a")
        assert sr is not None
        assert sr["repetitions"] == 1


class TestDisputeHandler:
    @pytest.mark.asyncio
    async def test_dispute_empty_reasoning(self, _reload_config, tmp_path):
        from coach.bot import on_dispute
        from coach.store import Store, init_db

        store = Store(init_db(tmp_path / "test.db"))
        update = _make_update("/dispute")
        context = MagicMock()
        context.bot_data = {"store": store, "grader": MagicMock()}
        context.args = []

        await on_dispute(update, context)
        reply = update.message.reply_text.call_args[0][0]
        assert "Usage" in reply

    @pytest.mark.asyncio
    async def test_dispute_no_deferred_grades(self, _reload_config, tmp_path):
        from coach.bot import on_dispute
        from coach.store import Store, init_db

        store = Store(init_db(tmp_path / "test.db"))
        update = _make_update("/dispute")
        context = MagicMock()
        context.bot_data = {"store": store, "grader": MagicMock()}
        context.args = ["I", "disagree"]

        await on_dispute(update, context)
        reply = update.message.reply_text.call_args[0][0]
        assert "No disputed" in reply
