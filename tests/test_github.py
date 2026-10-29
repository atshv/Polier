"""core/github.py: read-only GitHub/CI status with graceful fallbacks."""
from __future__ import annotations

import json
import unittest
from unittest import mock

from dash_helpers import sample_project

from core import github

PRS = [{"number": 7, "title": "P6 task", "state": "OPEN", "url": "https://example/pull/7",
        "headRefName": "task/ENG-01", "isDraft": False, "updatedAt": "2026-10-29T10:00:00Z",
        "statusCheckRollup": [{"conclusion": "SUCCESS"}, {"state": "SUCCESS"}]}]
RUNS = [{"databaseId": 1, "name": "CI", "status": "completed", "conclusion": "success",
         "headBranch": "task/ENG-01", "url": "https://example/run/1",
         "createdAt": "2026-10-29T10:00:00Z", "event": "pull_request"}]


class GithubTest(unittest.TestCase):
    def setUp(self) -> None:
        github.clear_cache()
        self.root = sample_project()

    def test_unavailable_without_remote(self) -> None:
        value = github.status(self.root)
        self.assertFalse(value["available"])
        self.assertIn("reason", value)

    def test_maps_prs_and_runs_to_tasks(self) -> None:
        with mock.patch.object(github, "_remote", return_value=("owner", "repo", "https://github.com/owner/repo")), \
                mock.patch.object(github, "_gh") as gh:
            gh.side_effect = [
                (True, json.dumps(PRS), ""),
                (True, json.dumps(RUNS), ""),
            ]
            value = github.status(self.root)
        self.assertTrue(value["available"])
        self.assertEqual(value["repo"], "owner/repo")
        self.assertEqual(value["counts"]["prs"], 1)
        self.assertIn("ENG-01", value["tasks"])
        self.assertEqual(value["tasks"]["ENG-01"]["pr"]["checks"], "pass")
        self.assertEqual(value["tasks"]["ENG-01"]["ci"]["conclusion"], "success")

    def test_gh_failure_is_graceful(self) -> None:
        with mock.patch.object(github, "_remote", return_value=("owner", "repo", "url")), \
                mock.patch.object(github, "_gh", return_value=(False, "", "authentication failed")):
            value = github.status(self.root)
        self.assertFalse(value["available"])
        self.assertIn("authentication", value["reason"])


if __name__ == "__main__":
    unittest.main()
