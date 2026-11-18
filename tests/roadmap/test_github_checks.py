"""GitHub pipeline state combines commit statuses and GitHub Actions check runs."""

from __future__ import annotations

import unittest

import helpers  # noqa: F401  (puts the roadmap scripts on sys.path)
from roadmaplib import forge

PROJECT = "o/r"
SHA = "abc123"


def pr_with(status=None, runs=None):
    responses = {}
    if status is not None:
        responses[f"GET repos/{PROJECT}/commits/{SHA}/status"] = status
    if runs is not None:
        responses[f"GET repos/{PROJECT}/commits/{SHA}/check-runs"] = {"total_count": len(runs), "check_runs": runs}
    fg = forge.GitHub(forge.RecordedTransport(responses), host="github.com", project=PROJECT)
    pr = {"state": "open", "head_sha": SHA, "project": PROJECT, "url": "https://github.com/o/r/pull/1",
          "pipeline": None, "pipeline_url": None}
    return fg._with_checks(pr)


def run(status="completed", conclusion="success"):
    return {"status": status, "conclusion": conclusion, "name": "ci"}


NO_STATUSES = {"state": "pending", "total_count": 0, "statuses": []}   # what GitHub says for an Actions-only repo


class ActionsOnlyRepos(unittest.TestCase):
    def test_green_check_runs_with_no_commit_statuses_are_success(self):
        self.assertEqual(pr_with(NO_STATUSES, [run(), run(conclusion="skipped")])["pipeline"], "success")

    def test_a_failed_check_run_is_failure_even_when_statuses_pass(self):
        ok = {"state": "success", "total_count": 1, "statuses": [{"state": "success"}]}
        self.assertEqual(pr_with(ok, [run(), run(conclusion="failure")])["pipeline"], "failure")

    def test_a_check_run_still_running_is_pending(self):
        got = pr_with(NO_STATUSES, [run(), run(status="in_progress", conclusion=None)])
        self.assertEqual(got["pipeline"], "pending")

    def test_a_pending_status_keeps_the_pipeline_pending(self):
        pending = {"state": "pending", "total_count": 1, "statuses": [{"state": "pending"}]}
        self.assertEqual(pr_with(pending, [run()])["pipeline"], "pending")

    def test_statuses_alone_still_work(self):
        self.assertEqual(pr_with({"state": "success"})["pipeline"], "success")

    def test_no_signal_at_all_leaves_the_pipeline_unknown(self):
        self.assertIsNone(pr_with(NO_STATUSES, [])["pipeline"])
        self.assertIsNone(pr_with()["pipeline"])


if __name__ == "__main__":
    unittest.main()
