"""check-mr: a merge request must name an issue on the agreed roadmap (forge enforcement, layer 1)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import CLI, SKILL, example, issue

from roadmaplib import checkmr

REPO = "example-org/search-service"


def check(title="", body="", project=REPO, data=None):
    return checkmr.check(data or example(), title, body, project)


class Names(unittest.TestCase):
    def test_a_closing_reference_to_a_roadmap_issue_passes(self):
        result = check("Rank by open rate", "Closes #12")
        self.assertTrue(result.ok, result.message)
        self.assertEqual(result.issue, "ranking-model")

    def test_the_roadmap_issue_line_with_a_short_name_passes(self):
        result = check("Results page", "Roadmap issue: page-build\n\nBuilds it.")
        self.assertTrue(result.ok, result.message)
        self.assertEqual(result.issue, "page-build")

    def test_a_full_reference_or_url_passes(self):
        self.assertTrue(check("x", f"Part of {REPO}#12").ok)
        self.assertTrue(check("x", f"See https://github.com/{REPO}/issues/11").ok)
        self.assertTrue(check("page-design: layout", "").ok)

    def test_naming_nothing_fails_and_says_what_to_add(self):
        result = check("Tidy the docs", "Small cleanup.")
        self.assertFalse(result.ok)
        self.assertIn("Roadmap issue:", result.message)

    def test_an_issue_not_on_the_roadmap_fails(self):
        result = check("x", "Closes #99")
        self.assertFalse(result.ok)

    def test_a_number_in_another_project_does_not_count(self):
        self.assertFalse(check("x", "Closes #12", project="someone/else").ok)

    def test_a_draft_roadmap_fails(self):
        data = example()
        data["agreed"] = False
        result = check("x", "Closes #12", data=data)
        self.assertFalse(result.ok)
        self.assertIn("agreed", result.message)

    def test_a_short_name_inside_another_word_does_not_count(self):
        self.assertFalse(check("x", "rewrite the page-builder").ok)

    def test_started_early_is_a_warning(self):
        result = check("x", "Roadmap issue: page-build")    # depends on page-design, still In review
        self.assertTrue(result.ok)
        self.assertTrue(any("page-design" in w for w in result.warnings))


class FromCI(unittest.TestCase):
    def run_cli(self, env, roadmap=None):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "roadmap.json"
            path.write_text(json.dumps(roadmap or example()))
            full_env = {k: v for k, v in os.environ.items() if not k.startswith(("CI_", "GITLAB", "GITHUB", "FORGEJO",
                                                                                  "GITEA"))}
            full_env.update({k: v.replace("{tmp}", tmp) for k, v in env.items()})
            if "event" in env:
                Path(tmp, "event.json").write_text(env["event"])
            return subprocess.run([sys.executable, str(CLI), "check-mr", str(path), "--from-ci"],
                                  capture_output=True, text=True, env=full_env)

    def test_gitlab_merge_request_pipeline(self):
        data = example()
        data["forge"] = {"kind": "gitlab", "host": "gitlab.example.com", "project": "acme/search"}
        issue(data, "ranking-model")["ref"] = "acme/search#12"
        ok = self.run_cli({"GITLAB_CI": "true", "CI_MERGE_REQUEST_TITLE": "Rank",
                           "CI_MERGE_REQUEST_DESCRIPTION": "Closes #12",
                           "CI_MERGE_REQUEST_PROJECT_PATH": "acme/search"}, data)
        self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)
        bad = self.run_cli({"GITLAB_CI": "true", "CI_MERGE_REQUEST_TITLE": "Rank",
                            "CI_MERGE_REQUEST_DESCRIPTION": "", "CI_MERGE_REQUEST_PROJECT_PATH": "acme/search"}, data)
        self.assertEqual(bad.returncode, 1)
        self.assertIn("Roadmap issue:", bad.stdout)

    def test_github_and_forgejo_actions_event(self):
        event = json.dumps({"pull_request": {"title": "Rank", "body": "Fixes #12"}})
        for flag in ("GITHUB_ACTIONS", "FORGEJO_ACTIONS"):
            with self.subTest(flag=flag):
                res = self.run_cli({flag: "true", "GITHUB_EVENT_PATH": "{tmp}/event.json", "GITHUB_REPOSITORY": REPO,
                                    "event": event})
                self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

    def test_outside_a_merge_request_pipeline_is_an_error(self):
        res = self.run_cli({})
        self.assertEqual(res.returncode, 2)


class Templates(unittest.TestCase):
    def test_each_forge_has_a_merge_request_template_and_ci_jobs(self):
        t = SKILL / "templates"
        for path in ("gitlab/merge_request_templates/Default.md", "github/pull_request_template.md",
                     "forgejo/pull_request_template.md"):
            text = (t / path).read_text()
            self.assertIn("Roadmap issue:", text, path)
            self.assertIn("Closes #", text, path)
        for path in ("gitlab/roadmap.gitlab-ci.yml", "github/workflows/roadmap-check.yml",
                     "forgejo/workflows/roadmap-check.yml"):
            self.assertIn("check-mr roadmap.json --from-ci", (t / path).read_text(), path)
        for path in ("gitlab/roadmap.gitlab-ci.yml", "github/workflows/roadmap-sync.yml",
                     "forgejo/workflows/roadmap-sync.yml"):
            text = (t / path).read_text()
            self.assertIn("sync roadmap.json --no-orca --write --update-epics", text, path)
            self.assertIn("drift-issue roadmap.json --no-orca --apply", text, path)


if __name__ == "__main__":
    unittest.main()
