"""drift-issue: one "Roadmap drift" issue, created once, updated in place, closed when drift is zero.

It is the only thing the tool ever closes, and only after re-reading the issue
and finding its own title and marker block.
"""

from __future__ import annotations

import unittest

from fakeforge import FakeGitHub, github
from helpers import example, issue

from roadmaplib import blocks, driftissue, forge, sync

REPO = "example-org/search-service"
NOW = "2026-11-17"


def drifting() -> dict:
    """The example roadmap: several issues are not on the forge yet, which is drift."""
    return example()


def quiet() -> dict:
    """A roadmap with no drift against fresh_forge()."""
    data = example()
    data["epics"] = data["epics"][:1]
    data["issues"] = [issue(data, "click-signals")]
    return data


def fresh_forge() -> FakeGitHub:
    fake = FakeGitHub()
    fake.add_issue(REPO, 10, "Better ranking", "Ranking work.")
    fake.add_issue(REPO, 11, "Record which results people open", "Anonymous counts.", state="closed")
    fake.add_issue(REPO, 12, "Rank results by open rate", "Blend.")
    fake.sub_issues[(REPO, 10)] = [fake.issues[(REPO, 11)]["id"]]
    return fake


def run(data, fake, apply=True):
    fg = github(fake)
    report = sync.sync(data, fg, orca_tasks=None, now=NOW)
    return driftissue.run(data, fg, report, apply=apply, today=NOW)


def drift_issues(fake):
    return [d for d in fake.issues.values() if d["title"] == "Roadmap drift"]


class OneDriftIssue(unittest.TestCase):
    def test_created_once_then_left_alone_while_nothing_changes(self):
        fake = fresh_forge()
        dry = run(drifting(), fake, apply=False)
        self.assertEqual([a.kind for a in dry.actions], ["create-drift-issue"])
        self.assertEqual(fake.writes, [])
        run(drifting(), fake)
        self.assertEqual(len(drift_issues(fake)), 1)
        body = drift_issues(fake)[0]["body"]
        self.assertIn("not-published", body)
        self.assertIsNotNone(blocks.block_content(body, blocks.DRIFT_START, blocks.DRIFT_END))
        n = len(fake.writes)
        run(drifting(), fake)
        self.assertEqual(len(fake.writes), n)

    def test_updated_in_place_when_drift_changes(self):
        fake = fresh_forge()
        run(drifting(), fake)
        data = drifting()
        data["issues"] = [i for i in data["issues"] if i["id"] != "weekly-release"]
        result = run(data, fake)
        self.assertEqual([a.kind for a in result.actions], ["update-drift-issue"])
        self.assertEqual(len(drift_issues(fake)), 1)
        self.assertNotIn("weekly-release", drift_issues(fake)[0]["body"])

    def test_closed_when_drift_is_zero(self):
        fake = fresh_forge()
        run(drifting(), fake)
        result = run(quiet(), fake)
        self.assertEqual([a.kind for a in result.actions], ["close-drift-issue"])
        self.assertEqual(drift_issues(fake)[0]["state"], "closed")
        self.assertEqual(fake.issues[(REPO, 12)]["state"], "open")

    def test_nothing_when_there_is_no_drift_and_no_issue(self):
        fake = fresh_forge()
        self.assertEqual(run(quiet(), fake).actions, [])
        self.assertEqual(fake.writes, [])

    def test_an_incomplete_sync_neither_closes_nor_rewrites(self):
        fake = fresh_forge()
        run(drifting(), fake)
        n = len(fake.writes)
        fg = github(fake)
        report = sync.sync(quiet(), fg, orca_tasks=None, now=NOW)
        report.errors.append("ranking-model: reading failed: HTTP 502")
        result = driftissue.run(quiet(), fg, report, apply=True, today=NOW)
        self.assertEqual(len(fake.writes), n)
        self.assertTrue(result.notes)

    def test_an_issue_a_person_titled_roadmap_drift_is_not_touched(self):
        fake = fresh_forge()
        mine = fake.add_issue(REPO, 30, "Roadmap drift", "My own notes.")
        run(drifting(), fake)
        self.assertEqual(fake.issues[(REPO, 30)]["body"], "My own notes.")
        run(quiet(), fake)
        self.assertEqual(mine["state"], "open")


class CloseIsNarrow(unittest.TestCase):
    def test_close_refuses_any_issue_that_is_not_the_drift_issue(self):
        fake = fresh_forge()
        fg = github(fake)
        with self.assertRaises(forge.ForgeError):
            fg.close_drift_issue(fg.get_issue(f"{REPO}#12"))
        self.assertEqual(fake.issues[(REPO, 12)]["state"], "open")

    def test_the_guard_allows_only_a_bare_close(self):
        guard = forge.WriteGuard()
        guard.check("PATCH", "repos/o/r/issues/5", {"state": "closed"}, allow_close=True)
        guard.check("PUT", "projects/1/issues/5", {"state_event": "close"}, allow_close=True)
        for method, body in (("DELETE", None), ("PATCH", {"state": "closed", "title": "x"}),
                             ("PATCH", {"state": "closed", "body": "y"})):
            with self.subTest(method=method, body=body), self.assertRaises(forge.ForgeError):
                guard.check(method, "repos/o/r/issues/5", body, allow_close=True)
        with self.assertRaises(forge.ForgeError):
            guard.check("PATCH", "repos/o/r/issues/5", {"state": "closed"})


if __name__ == "__main__":
    unittest.main()
