"""drift-issue: one "Roadmap drift" issue, created once, updated in place, closed when drift is zero.

It is the only thing the tool ever closes, and only after re-reading the issue
and finding its own title and marker block.
"""

from __future__ import annotations

import unittest
from unittest import mock

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

    def test_an_untouched_backlog_does_not_keep_the_issue_open(self):
        fake = fresh_forge()
        run(drifting(), fake)
        fake.issues[(REPO, 12)]["updated_at"] = "2025-01-01T00:00:00Z"
        data = quiet()
        data["issues"].append(dict(issue(example(), "ranking-model"), status="to_do"))
        result = run(data, fake)
        self.assertEqual([a.kind for a in result.actions], ["close-drift-issue"])

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


class OnlyItsOwnIssue(unittest.TestCase):
    """Anyone can open an issue titled "Roadmap drift" with the markers; only the tool's own counts."""

    def test_a_strangers_drift_issue_is_never_taken_over_or_closed(self):
        fake = fresh_forge()
        body = f"Look here.\n{blocks.DRIFT_START}\n- nothing\n{blocks.DRIFT_END}"
        fake.add_issue(REPO, 40, "Roadmap drift", body, author="stranger")
        result = run(drifting(), fake)
        self.assertEqual([a.kind for a in result.actions], ["create-drift-issue"])
        self.assertEqual(fake.issues[(REPO, 40)]["body"], body)
        run(quiet(), fake)
        self.assertEqual(fake.issues[(REPO, 40)]["state"], "open")
        own = [d for d in drift_issues(fake) if d["user"]["login"] == "roadmap-bot"]
        self.assertEqual([d["state"] for d in own], ["closed"])

    def test_apply_refuses_when_the_token_user_is_unknown(self):
        fake = fresh_forge()
        run(drifting(), fake)
        n = len(fake.writes)
        fake.me = None
        with self.assertRaises(forge.ForgeError):
            run(quiet(), fake)
        self.assertEqual(len(fake.writes), n)
        dry = run(quiet(), fake, apply=False)
        self.assertTrue(any("token" in note for note in dry.notes))

    def test_in_github_actions_the_workflow_token_is_the_actions_bot(self):
        """GITHUB_TOKEN cannot read GET /user (403); issues it opens are by github-actions[bot]."""
        fake = fresh_forge()
        fake.user_error = "gh api user failed: gh: Resource not accessible by integration (HTTP 403)"
        with mock.patch.dict("os.environ", {"GITHUB_ACTIONS": "true"}):
            self.assertEqual(github(fake).current_user(), "github-actions[bot]")
        with mock.patch.dict("os.environ", {}, clear=True), self.assertRaises(forge.ForgeError):
            github(fake).current_user()

    def test_in_github_actions_any_other_failure_is_not_the_actions_bot(self):
        """A rate limit, a server error or no network says nothing about whose token it is."""
        for error in ("gh api user failed: HTTP 401: Bad credentials", "gh api user failed: HTTP 502",
                      "gh api user failed: API rate limit exceeded (HTTP 403)",
                      "GET user failed: the forge could not be reached"):
            with self.subTest(error=error), mock.patch.dict("os.environ", {"GITHUB_ACTIONS": "true"}):
                fake = fresh_forge()
                run(drifting(), fake)
                self.assertEqual(len(drift_issues(fake)), 1)
                n = len(fake.writes)
                fake.user_error = error
                with self.assertRaises(forge.ForgeError):
                    github(fake).current_user()
                with self.assertRaises(forge.ForgeError):
                    run(drifting(), fake)
                self.assertEqual(len(fake.writes), n)
                self.assertEqual(len(drift_issues(fake)), 1)


class AdoptsOnlyItsOwnIssue(unittest.TestCase):
    """An issue by the same user with the title and markers is adopted only if it holds the tool's text alone."""

    def test_text_the_tool_did_not_write_is_not_adopted(self):
        fake = fresh_forge()
        own = driftissue.skeleton("- **old** item: gone")
        for body in ("Phishing link here.\n\n" + own, own + "\n\nPhishing link here.",
                     own.replace(driftissue.INTRO, "Something else entirely.")):
            with self.subTest(body=body[:40]):
                fake = fresh_forge()
                fake.add_issue(REPO, 50, "Roadmap drift", body)
                result = run(drifting(), fake)
                self.assertEqual([a.kind for a in result.actions], ["create-drift-issue"])
                self.assertEqual(fake.issues[(REPO, 50)]["body"], body)
                self.assertTrue(any(f"{REPO}#50" in n for n in result.notes), result.notes)
                run(quiet(), fake)
                self.assertEqual(fake.issues[(REPO, 50)]["state"], "open")

    def test_the_tools_own_text_is_adopted(self):
        fake = fresh_forge()
        fake.add_issue(REPO, 50, "Roadmap drift", driftissue.skeleton("- **old** item: gone").replace("\n", "\r\n"))
        result = run(drifting(), fake)
        self.assertEqual([a.kind for a in result.actions], ["update-drift-issue"])
        self.assertEqual(len(drift_issues(fake)), 1)

    def test_close_rereads_the_author(self):
        fake = fresh_forge()
        body = f"{blocks.DRIFT_START}\n- x\n{blocks.DRIFT_END}"
        fake.add_issue(REPO, 41, "Roadmap drift", body, author="stranger")
        fg = github(fake)
        with self.assertRaises(forge.ForgeError):
            fg.close_drift_issue(fg.get_issue(f"{REPO}#41"), author="roadmap-bot")
        self.assertEqual(fake.issues[(REPO, 41)]["state"], "open")


class HandTextOnGitLab(unittest.TestCase):
    def test_hand_text_with_a_live_command_is_never_written(self):
        """Hand text outside the markers means the issue is not the tool's own: it is left alone."""
        fake = fresh_forge()
        run(drifting(), fake)
        mine = drift_issues(fake)[0]
        mine["body"] = "Notes.\n/close\n" + mine["body"]
        before = mine["body"]
        fg = github(fake)
        fg.kind = "gitlab"   # GitLab runs quick actions; the fake answers like GitHub otherwise
        data = drifting()
        data["issues"] = [i for i in data["issues"] if i["id"] != "weekly-release"]
        result = driftissue.run(data, fg, sync.sync(data, fg, orca_tasks=None, now=NOW), apply=True, today=NOW)
        self.assertEqual(mine["body"], before)
        self.assertNotIn(("PATCH", f"repos/{REPO}/issues/{mine['number']}"), [w[:2] for w in fake.writes])
        self.assertEqual([a.kind for a in result.actions], ["create-drift-issue"])


class CloseIsNarrow(unittest.TestCase):
    def test_close_refuses_any_issue_that_is_not_the_drift_issue(self):
        fake = fresh_forge()
        fg = github(fake)
        with self.assertRaises(forge.ForgeError):
            fg.close_drift_issue(fg.get_issue(f"{REPO}#12"), "roadmap-bot")
        self.assertEqual(fake.issues[(REPO, 12)]["state"], "open")

    def test_gitlab_rereads_the_issue_before_closing(self):
        """The caller's copy may be stale or forged: only the forge's own answer counts."""
        def gitlab_issue(title, body, state="opened", author="roadmap-bot"):
            return {"id": 1, "iid": 40, "project_id": 7, "title": title, "description": body, "state": state,
                    "author": {"username": author},
                    "references": {"full": "acme/search#40"}, "web_url": "https://gitlab.example.com/acme/search/-/issues/40"}

        drift_body = f"{blocks.DRIFT_START}\n- x\n{blocks.DRIFT_END}"
        stale = forge.GitLab(None, "gitlab.example.com", "acme/search", "acme")._issue(
            gitlab_issue("Roadmap drift", drift_body))
        for now in (gitlab_issue("Ship the ranking model", "Real work."),
                    gitlab_issue("Roadmap drift", "Markers removed by a person."),
                    gitlab_issue("Roadmap drift", drift_body, state="closed"),
                    gitlab_issue("Roadmap drift", drift_body, author="stranger")):
            writes = []

            class Recording(forge.RecordedTransport):
                def send(self, method, path, body=None, allow_close=False):
                    writes.append((method, path, body))

            fg = forge.GitLab(Recording({"GET projects/acme%2Fsearch/issues/40": now}), "gitlab.example.com",
                              "acme/search", "acme")
            with self.subTest(title=now["title"], state=now["state"], author=now["author"]), \
                    self.assertRaises(forge.ForgeError):
                fg.close_drift_issue(stale, "roadmap-bot")
            self.assertEqual(writes, [])

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
