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
        """check-mr --from-ci in a scratch repository whose one commit, the base, holds the roadmap."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "roadmap.json"
            path.write_text(json.dumps(roadmap or example()))
            for args in (["init", "-q"], ["add", "roadmap.json"],
                         ["-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-qm", "base"]):
                subprocess.run(["git", "-C", tmp, *args], capture_output=True, check=True)
            base = subprocess.run(["git", "-C", tmp, "rev-parse", "HEAD"], capture_output=True, text=True,
                                  check=True).stdout.strip()
            full_env = {k: v for k, v in os.environ.items() if not k.startswith(("CI_", "GITLAB", "GITHUB", "FORGEJO",
                                                                                  "GITEA"))}
            full_env.update({k: v.replace("{tmp}", tmp) for k, v in env.items()})
            if "GITLAB_CI" in env:
                full_env.setdefault("CI_MERGE_REQUEST_DIFF_BASE_SHA", base)
            if "event" in env:
                event = json.loads(env["event"])
                event.get("pull_request", {}).setdefault("base", {"sha": base})
                Path(tmp, "event.json").write_text(json.dumps(event))
            return subprocess.run([sys.executable, str(CLI), "check-mr", "roadmap.json", "--from-ci"],
                                  capture_output=True, text=True, env=full_env, cwd=tmp)

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


class RoadmapChanges(unittest.TestCase):
    """The merge request that changes the roadmap itself has no roadmap issue to name."""

    def test_a_change_to_only_the_roadmap_and_its_page_passes(self):
        draft = dict(example(), agreed=False)
        for data in (example(), draft):
            for changed in (["roadmap.json"], ["roadmap.json", "roadmap.html"], ["./roadmap.json"]):
                with self.subTest(agreed=data["agreed"], changed=changed):
                    result = checkmr.check(data, "Agree version 4", "", REPO, changed=changed,
                                           roadmap_path="roadmap.json")
                    self.assertTrue(result.ok, result.message)
                    self.assertIn("only the roadmap", result.message)

    def test_any_other_file_needs_a_roadmap_issue(self):
        for changed in (["roadmap.json", "src/rank.py"], ["docs/roadmap.json"], []):
            with self.subTest(changed=changed):
                result = checkmr.check(example(), "Agree version 4", "", REPO, changed=changed,
                                       roadmap_path="roadmap.json")
                self.assertFalse(result.ok)

    def git(self, repo, *args):
        return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout

    def repo_with_change(self, tmp, files):
        repo = Path(tmp)
        self.git(repo, "init", "-q")
        self.git(repo, "config", "user.email", "t@example.com")
        self.git(repo, "config", "user.name", "t")
        (repo / "roadmap.json").write_text(json.dumps(example()))
        self.git(repo, "add", ".")
        self.git(repo, "commit", "-qm", "base")
        base = self.git(repo, "rev-parse", "HEAD").strip()
        for name in files:
            (repo / name).parent.mkdir(parents=True, exist_ok=True)
            (repo / name).write_text("changed\n" if name != "roadmap.json" else json.dumps(dict(example(), version="4")))
        self.git(repo, "add", ".")
        self.git(repo, "commit", "-qm", "change")
        return repo, base

    def run_ci(self, files, gitlab=True):
        with tempfile.TemporaryDirectory() as tmp:
            repo, base = self.repo_with_change(tmp, files)
            env = {k: v for k, v in os.environ.items() if not k.startswith(("CI_", "GITLAB", "GITHUB", "FORGEJO",
                                                                            "GITEA"))}
            if gitlab:
                env.update({"GITLAB_CI": "true", "CI_MERGE_REQUEST_TITLE": "Agree version 4",
                            "CI_MERGE_REQUEST_DESCRIPTION": "", "CI_MERGE_REQUEST_PROJECT_PATH": REPO,
                            "CI_MERGE_REQUEST_DIFF_BASE_SHA": base})
            else:
                event = repo.parent / f"{repo.name}-event.json"
                event.write_text(json.dumps({"pull_request": {"title": "Agree version 4", "body": "",
                                                              "base": {"sha": base}}}))
                env.update({"GITHUB_ACTIONS": "true", "GITHUB_EVENT_PATH": str(event), "GITHUB_REPOSITORY": REPO})
            return subprocess.run([sys.executable, str(CLI), "check-mr", "roadmap.json", "--from-ci"],
                                  capture_output=True, text=True, env=env, cwd=repo)

    def test_in_ci_the_changed_files_come_from_git(self):
        for gitlab in (True, False):
            with self.subTest(gitlab=gitlab):
                ok = self.run_ci(["roadmap.json"], gitlab)
                self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)
                bad = self.run_ci(["roadmap.json", "src/rank.py"], gitlab)
                self.assertEqual(bad.returncode, 1, bad.stdout + bad.stderr)

    def test_by_hand_the_changed_files_are_given(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "roadmap.json"
            path.write_text(json.dumps(example()))
            res = subprocess.run([sys.executable, str(CLI), "check-mr", str(path), "--title", "Agree version 4",
                                  "--changed", str(path)], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)


class JudgedByTheBaseRoadmap(unittest.TestCase):
    """In CI the roadmap is read from the merge request's base commit, never from the change it judges."""

    def git(self, repo, *args):
        return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout

    def run_ci(self, base_files, change, title, gitlab=True, base_sha=None, no_base=False):
        """A scratch repository: commit base_files, apply change(repo), commit, and run check-mr --from-ci."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            self.git(repo, "init", "-q")
            self.git(repo, "config", "user.email", "t@example.com")
            self.git(repo, "config", "user.name", "t")
            for name, text in base_files.items():
                (repo / name).write_text(text)
            self.git(repo, "add", ".")
            self.git(repo, "commit", "-qm", "base")
            base = base_sha or self.git(repo, "rev-parse", "HEAD").strip()
            change(repo)
            self.git(repo, "add", "-A")
            self.git(repo, "commit", "-qm", "change")
            env = {k: v for k, v in os.environ.items()
                   if not k.startswith(("CI_", "GITLAB", "GITHUB", "FORGEJO", "GITEA"))}
            if gitlab:
                env.update({"GITLAB_CI": "true", "CI_MERGE_REQUEST_TITLE": title,
                            "CI_MERGE_REQUEST_DESCRIPTION": "", "CI_MERGE_REQUEST_PROJECT_PATH": REPO,
                            "CI_MERGE_REQUEST_DIFF_BASE_SHA": "" if no_base else base})
            else:
                event = Path(tmp) / "event.json"
                pr = {"title": title, "body": "", "base": {} if no_base else {"sha": base}}
                event.write_text(json.dumps({"pull_request": pr}))
                env.update({"GITHUB_ACTIONS": "true", "GITHUB_EVENT_PATH": str(event), "GITHUB_REPOSITORY": REPO})
            return subprocess.run([sys.executable, str(CLI), "check-mr", "roadmap.json", "--from-ci"],
                                  capture_output=True, text=True, env=env, cwd=repo)

    @staticmethod
    def add_own_issue(agreed=True):
        def change(repo):
            data = json.loads((repo / "roadmap.json").read_text())
            data["agreed"] = agreed
            data["issues"].append(dict(issue(data, "page-build"), id="my-side-thing", title="My side thing"))
            (repo / "roadmap.json").write_text(json.dumps(data))
            (repo / "app.py").write_text("print('changed')\n")
        return change

    def test_a_merge_request_cannot_add_and_name_its_own_issue(self):
        base = {"roadmap.json": json.dumps(example()), "app.py": "print('base')\n"}
        for gitlab in (True, False):
            with self.subTest(gitlab=gitlab):
                res = self.run_ci(base, self.add_own_issue(), "my-side-thing: tweak", gitlab)
                self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
                self.assertIn("names no issue on the agreed roadmap", res.stdout)
                ok = self.run_ci(base, self.add_own_issue(), "ranking-model: tweak", gitlab)
                self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)

    def test_a_merge_request_cannot_agree_a_draft_and_use_it(self):
        base = {"roadmap.json": json.dumps(dict(example(), agreed=False)), "app.py": "print('base')\n"}
        res = self.run_ci(base, self.add_own_issue(agreed=True), "ranking-model: tweak")
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("draft", res.stdout)

    def test_a_merge_request_that_adds_the_roadmap_with_code_fails(self):
        def change(repo):
            (repo / "roadmap.json").write_text(json.dumps(example()))
            (repo / "app.py").write_text("print('changed')\n")
        res = self.run_ci({"app.py": "print('base')\n"}, change, "ranking-model: tweak")
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("no roadmap.json", res.stdout)

    def test_a_base_commit_git_cannot_find_stops_the_check(self):
        base = {"roadmap.json": json.dumps(example()), "app.py": "print('base')\n"}
        res = self.run_ci(base, self.add_own_issue(), "my-side-thing: tweak", base_sha="0123456789abcdef0123")
        self.assertEqual(res.returncode, 2, res.stdout + res.stderr)
        self.assertIn("full history", res.stdout)

    def test_no_base_commit_from_the_forge_stops_the_check(self):
        """Without a base commit the only roadmap at hand is the merge request's own: never trust it."""
        base = {"roadmap.json": json.dumps(example()), "app.py": "print('base')\n"}
        for gitlab in (True, False):
            with self.subTest(gitlab=gitlab):
                res = self.run_ci(base, self.add_own_issue(), "my-side-thing: tweak", gitlab, no_base=True)
                self.assertEqual(res.returncode, 2, res.stdout + res.stderr)
                self.assertIn("no base commit", res.stdout)
                self.assertNotIn("OK:", res.stdout)

    def test_renaming_code_to_the_roadmap_page_is_not_a_roadmap_change(self):
        base = {"roadmap.json": json.dumps(example()), "core.py": "def main():\n    return 1\n" * 20}

        def change(repo):
            self.git(repo, "mv", "core.py", "roadmap.html")
        res = self.run_ci(base, change, "tidy")
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertNotIn("only the roadmap", res.stdout)


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
            text = (t / path).read_text()
            self.assertIn("check-mr roadmap.json --from-ci", text, path)
            # The changed files are read from git, so the job needs history and git.
            self.assertTrue("fetch-depth: 0" in text or 'GIT_DEPTH: "0"' in text, path)
            self.assertNotIn("-slim", text.split("roadmap-sync")[0], path)
        for path in ("gitlab/roadmap.gitlab-ci.yml", "github/workflows/roadmap-sync.yml",
                     "forgejo/workflows/roadmap-sync.yml"):
            text = (t / path).read_text()
            self.assertIn("sync roadmap.json --no-orca --write --update-epics", text, path)
            self.assertIn("drift-issue roadmap.json --no-orca --apply", text, path)

    def test_the_gitlab_sync_job_clears_the_glab_image_entrypoint(self):
        # The glab image's ENTRYPOINT is glab, so a script run by the image would be
        # passed to glab as arguments. The job must reset it.
        text = (SKILL / "templates" / "gitlab" / "roadmap.gitlab-ci.yml").read_text()
        job = text.split("roadmap-sync:")[1]
        self.assertRegex(job, r'image:\s*\n\s+name: registry\.gitlab\.com/gitlab-org/cli:v[\d.]+\s*\n'
                              r'\s+entrypoint: \[""\]')


if __name__ == "__main__":
    unittest.main()
