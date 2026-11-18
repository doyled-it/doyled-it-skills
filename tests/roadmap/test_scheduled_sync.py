"""The scheduled run syncs once, and finds the drift issue without paging through every issue."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from fakeforge import github
from helpers import example
from roadmaplib import cli, driftissue, forge, orca, sync
from test_drift_issue import NOW, REPO, drift_issues, fresh_forge
from test_fetch_once import CountingFake


class FindsTheDriftIssueAmongOpenIssues(unittest.TestCase):
    def test_no_read_asks_for_closed_issues(self):
        fake = CountingFake(fresh_forge())
        fg = forge.GitHub(fake, host="github.com", project=REPO)
        report = sync.sync(example(), fg, orca_tasks=None, now=NOW)
        fake.reads.clear()
        driftissue.run(example(), fg, report, apply=True, today=NOW)
        self.assertTrue(fake.reads)
        self.assertFalse([p for p in fake.reads if "state=all" in p], fake.reads)

    def test_a_closed_issue_with_the_title_is_not_in_the_listing(self):
        fake = fresh_forge()
        fake.add_issue(REPO, 31, "Roadmap drift", "old", state="closed")
        fg = github(fake)
        self.assertEqual([i["number"] for i in fg.open_issues_titled(REPO, "Roadmap drift")], [])

    def test_gitlab_and_forgejo_query_open_issues_by_title(self):
        seen = []

        class Spy(forge.RecordedTransport):
            def get_all(self, path):
                seen.append(path)
                return []

        forge.GitLab(Spy({}), host="gitlab.example.com", project="acme/search", group="acme") \
            .open_issues_titled("acme/search", "Roadmap drift")
        forge.Forgejo(Spy({}), host="codeberg.org", project=REPO).open_issues_titled(REPO, "Roadmap drift")
        self.assertEqual(len(seen), 2)
        for path in seen:
            self.assertIn("state=open", path.replace("state=opened", "state=open"))
            self.assertNotIn("state=all", path)
            self.assertIn("Roadmap", path)


class OneSyncPerScheduledRun(unittest.TestCase):
    def test_sync_can_update_the_drift_issue_from_its_own_report(self):
        fake = fresh_forge()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "roadmap.json"
            path.write_text(json.dumps(example()))
            real = sync.sync
            with mock.patch.object(forge, "from_args", return_value=github(fake)), \
                    mock.patch.object(orca, "tasks_from_args", return_value=None), \
                    mock.patch.object(sync, "sync", side_effect=real) as spy, \
                    redirect_stdout(io.StringIO()) as out:
                code = cli.main(["sync", str(path), "--no-orca", "--now", NOW, "--update-drift-issue"])
        self.assertEqual(spy.call_count, 1, out.getvalue())
        self.assertIn(code, (0, 1))
        self.assertEqual(len(drift_issues(fake)), 1)

    def test_the_scheduled_templates_run_one_sync_command(self):
        from helpers import SKILL

        for rel in ("gitlab/roadmap.gitlab-ci.yml", "github/workflows/roadmap-sync.yml",
                    "forgejo/workflows/roadmap-sync.yml"):
            text = (SKILL / "templates" / rel).read_text()
            self.assertIn("sync roadmap.json --no-orca --write --update-epics --update-drift-issue", text, rel)
            self.assertNotIn(" drift-issue roadmap.json", text, rel)


if __name__ == "__main__":
    unittest.main()
