"""Tests for the PR stager — mocks the GitHub API at the boundary."""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from coach.stager import PRStager, StagedPR


def _mock_response(json_data=None, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.raise_for_status = MagicMock()
    if json_data is not None:
        resp.json.return_value = json_data
    return resp


class TestPRStager:
    @patch("coach.stager.requests")
    def test_stage_lesson_opens_pr_on_lessons_staging(self, mock_requests):
        branch_resp = _mock_response({"commit": {"sha": "abc123"}})
        pr_resp = _mock_response({"number": 42, "html_url": "https://github.com/test/pr/42", "title": "Lesson 2026-08-01"})
        commit_resp = _mock_response({"content": {"sha": "def"}})
        mock_requests.get.return_value = branch_resp
        mock_requests.post.side_effect = [commit_resp, pr_resp]
        mock_requests.put.return_value = commit_resp

        stager = PRStager(token="test-token", repo="test/repo", branch="lessons-staging")
        result = stager.stage_lesson(
            lesson_data={"pm_concept": "p", "ai_concept": "a"},
            record_data=[{"grade": "meets"}],
            day=date(2026, 8, 1),
        )

        assert result.number == 42
        assert "github.com" in result.url
        # Verify PR was created with base=lessons-staging
        pr_call = mock_requests.post.call_args_list[-1]
        assert pr_call[1]["json"]["base"] == "lessons-staging"
        assert pr_call[1]["json"]["head"] == "lesson-2026-08-01"

    @patch("coach.stager.requests")
    def test_stage_lesson_never_commits_to_main(self, mock_requests):
        branch_resp = _mock_response({"commit": {"sha": "abc123"}})
        pr_resp = _mock_response({"number": 1, "html_url": "url", "title": "t"})
        commit_resp = _mock_response({"content": {"sha": "def"}})
        mock_requests.get.return_value = branch_resp
        mock_requests.post.side_effect = [commit_resp, pr_resp]
        mock_requests.put.return_value = commit_resp

        stager = PRStager(token="t", repo="r", branch="lessons-staging")
        stager.stage_lesson({"p": "a"}, [], date(2026, 8, 1))

        # Check no commit goes to main — all file commits go to the dated branch
        for call in mock_requests.put.call_args_list:
            assert call[1]["json"]["branch"] == "lesson-2026-08-01"

    @patch("coach.stager.requests")
    def test_stage_lesson_includes_lesson_and_record_files(self, mock_requests):
        branch_resp = _mock_response({"commit": {"sha": "abc123"}})
        pr_resp = _mock_response({"number": 1, "html_url": "url", "title": "t"})
        commit_resp = _mock_response({"content": {"sha": "def"}})
        mock_requests.get.return_value = branch_resp
        mock_requests.post.side_effect = [commit_resp, pr_resp]
        mock_requests.put.return_value = commit_resp

        stager = PRStager(token="t", repo="r", branch="lessons-staging")
        stager.stage_lesson(
            {"pm_concept": "p"}, [{"grade": "meets"}], date(2026, 8, 1),
        )

        committed_paths = [call[0][0].split("/contents/")[1] for call in mock_requests.put.call_args_list]
        assert any("lesson.json" in p for p in committed_paths)
        assert any("record.json" in p for p in committed_paths)
