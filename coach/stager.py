"""PR stager — stages lessons + learning records as PRs on lessons-staging.

Per #32 Phase 6: the nightly job stages every lesson + learning record as a PR
on the `lessons-staging` working branch. Never auto-commits to main; Manmeet is
the human gate. Uses the GitHub API via the gh CLI / REST API.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import requests

log = logging.getLogger("coach.stager")


@dataclass(frozen=True)
class StagedPR:
    """A staged PR on lessons-staging."""

    number: int
    url: str
    title: str


class PRStager:
    """Stages lessons + records as PRs on the lessons-staging branch."""

    def __init__(self, token: str, repo: str, branch: str = "lessons-staging") -> None:
        self._token = token
        self._repo = repo
        self._branch = branch
        self._api = "https://api.github.com"
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def stage_lesson(
        self,
        lesson_data: dict[str, Any],
        record_data: list[dict[str, Any]],
        day: date,
    ) -> StagedPR:
        """Stage a lesson + its learning records as a PR.

        Creates a dated branch off lessons-staging, commits the lesson + record
        files, and opens a PR. Never commits to main.
        """
        date_str = day.isoformat()
        pr_branch = f"lesson-{date_str}"

        # Get the default branch SHA to branch from
        base_sha = self._get_branch_sha(self._branch)

        # Create the dated branch
        self._create_branch(pr_branch, base_sha)

        # Commit lesson file
        lesson_path = f"lessons/{date_str}/lesson.json"
        self._commit_file(pr_branch, lesson_path,
                          json.dumps(lesson_data, indent=2))

        # Commit record file
        if record_data:
            record_path = f"lessons/{date_str}/record.json"
            self._commit_file(pr_branch, record_path,
                              json.dumps(record_data, indent=2))

        # Open PR
        pr = self._create_pr(
            head=pr_branch,
            base=self._branch,
            title=f"Lesson {date_str}",
            body=f"Staged lesson + learning record for {date_str}.\n\n"
            f"Review and merge — this is the human gate.",
        )
        return StagedPR(number=pr["number"], url=pr["html_url"], title=pr["title"])

    def _get_branch_sha(self, branch: str) -> str:
        resp = requests.get(
            f"{self._api}/repos/{self._repo}/branches/{branch}",
            headers=self._headers,
        )
        resp.raise_for_status()
        return resp.json()["commit"]["sha"]

    def _create_branch(self, branch: str, sha: str) -> None:
        resp = requests.post(
            f"{self._api}/repos/{self._repo}/git/refs",
            headers=self._headers,
            json={"ref": f"refs/heads/{branch}", "sha": sha},
        )
        if resp.status_code == 422:  # branch already exists
            log.info("branch %s already exists, reusing", branch)
            return
        resp.raise_for_status()

    def _commit_file(self, branch: str, path: str, content: str) -> None:
        import base64
        resp = requests.put(
            f"{self._api}/repos/{self._repo}/contents/{path}",
            headers=self._headers,
            json={
                "message": f"stage {path}",
                "content": base64.b64encode(content.encode()).decode(),
                "branch": branch,
            },
        )
        resp.raise_for_status()

    def _create_pr(self, head: str, base: str, title: str, body: str) -> dict:
        resp = requests.post(
            f"{self._api}/repos/{self._repo}/pulls",
            headers=self._headers,
            json={"title": title, "head": head, "base": base, "body": body},
        )
        resp.raise_for_status()
        return resp.json()
