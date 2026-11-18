"""Forgejo and Codeberg: issue dependencies, epics as parent issues with a generated section."""

from __future__ import annotations

import unittest
from unittest import mock

from helpers import example, fixture, issue
from roadmaplib import blocks, forge, publish, sync, validate
from test_publish import NoWrites


def forgejo_roadmap() -> dict:
    data = example()
    data["forge"] = {"kind": "forgejo", "host": "codeberg.org", "project": "example-org/search-service"}
    return data


def make(name):
    return forge.Forgejo(NoWrites(fixture(name)), host="codeberg.org", project="example-org/search-service")


class ForgejoPublish(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = publish.publish(forgejo_roadmap(), make("forgejo_publish.json"), apply=False)

    def kinds(self, kind):
        return [a for a in self.report.actions if a.kind == kind]

    def test_roadmap_with_forgejo_forge_validates(self):
        self.assertEqual(validate.errors(validate.check(forgejo_roadmap())), [])

    def test_epics_are_parent_issues_without_labels(self):
        self.assertEqual([a.target for a in self.kinds("link-epic")], ["ranking"])
        for a in self.kinds("create-epic"):
            self.assertIn("parent issue", a.detail)

    def test_membership_is_the_task_list_in_the_epic_section(self):
        added = {a.target: a.detail for a in self.kinds("add-to-epic")}
        self.assertIn("ranking-model", added)
        self.assertNotIn("click-signals", added)   # already listed in the parent issue
        self.assertIn("generated section", added["ranking-model"])
        ranking = next(a for a in self.kinds("update-epic") if a.target == "ranking")
        self.assertIn("### Issues in this epic", ranking.body)
        self.assertIn("example-org/search-service#12", ranking.body)
        self.assertIn("Ranking work, written by hand.", ranking.body)
        self.assertIn("More hand-written notes.", ranking.body)
        self.assertNotIn("old generated text", ranking.body)

    def test_blocked_by_uses_issue_dependencies(self):
        pairs = {(a.target, a.detail.split()[-1]) for a in self.kinds("add-blocked-by")}
        self.assertNotIn(("ranking-model", "click-signals"), pairs)
        self.assertEqual(len(pairs), 6)

    def test_never_uses_milestones_or_labels(self):
        for a in self.report.actions:
            self.assertNotIn("milestone", (a.detail + (a.body or "")).lower())
            self.assertNotIn("~", a.body or "")


class ForgejoSync(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        data = forgejo_roadmap()
        issue(data, "ranking-model")["gates"] = ["D", "R", "M"]
        cls.report = sync.sync(data, make("forgejo_sync.json"), orca_tasks=[], now="2026-11-17")

    def test_pull_request_states_and_commit_status(self):
        mrs = self.report.merge_requests
        self.assertEqual([m["state"] for m in mrs["click-signals"]], ["merged"])
        self.assertEqual(len(mrs["ranking-model"]), 1)      # duplicate timeline events collapse
        self.assertEqual(mrs["ranking-model"][0]["pipeline"], "success")

    def test_open_pull_request_moves_to_in_review(self):
        changes = {c.issue: c.new for c in self.report.status_changes}
        self.assertEqual(changes["ranking-model"], "in_review")

    def test_drift_from_the_parent_issue_task_list_and_pulls(self):
        kinds = {(d.kind, d.target) for d in self.report.drift}
        self.assertIn(("unlisted-epic-issue", "example-org/search-service#99"), kinds)
        self.assertIn(("unlinked-merge-request", "example-org/search-service#40"), kinds)
        self.assertNotIn(("unlinked-merge-request", "example-org/search-service#31"), kinds)


class ForgejoPinnedEpics(unittest.TestCase):
    """Codeberg's API cannot automate Projects, so parent issues can be pinned instead."""

    def run_publish(self, pin_order=0, allowed=True):
        responses = dict(fixture("forgejo_publish.json"))
        epic = dict(responses["GET repos/example-org/search-service/issues/10"], pin_order=pin_order)
        responses["GET repos/example-org/search-service/issues/10"] = epic
        responses["GET repos/example-org/search-service/new_pin_allowed"] = {"issues": allowed}
        data = forgejo_roadmap()
        data["forge"]["pin_epics"] = True
        fg = forge.make("forgejo", NoWrites(responses), data["forge"])
        report = publish.publish(data, fg, apply=False)
        return {a.target: a.detail for a in report.actions if a.kind == "pin-epic"}

    def test_unpinned_epics_are_pinned_when_asked(self):
        pins = self.run_publish()
        self.assertEqual(set(pins), {"ranking", "search-page", "release-safety"})

    def test_already_pinned_epic_is_left_alone(self):
        self.assertNotIn("ranking", self.run_publish(pin_order=1))

    def test_no_free_pin_slot_is_reported_not_forced(self):
        pins = self.run_publish(allowed=False)
        self.assertIn("no free pin slot", pins["ranking"])

    def test_pinning_is_off_by_default(self):
        actions = publish.publish(forgejo_roadmap(), make("forgejo_publish.json"), apply=False).actions
        self.assertFalse([a for a in actions if a.kind == "pin-epic"])


class ForgeChoice(unittest.TestCase):
    def test_codeberg_remote_means_forgejo(self):
        with mock.patch("subprocess.run") as run:
            run.return_value = mock.Mock(stdout="git@codeberg.org:example-org/search-service.git\n")
            self.assertEqual(forge.detect_from_remote("."), ("forgejo", "codeberg.org"))
            run.return_value = mock.Mock(stdout="https://github.com/o/r.git\n")
            self.assertEqual(forge.detect_from_remote("."), ("github", "github.com"))
            run.return_value = mock.Mock(stdout="git@gitlab.example.com:group/sub/app.git\n")
            self.assertEqual(forge.detect_from_remote("."), ("gitlab", "gitlab.example.com"))

    def test_gitea_is_accepted_as_forgejo(self):
        self.assertIs(forge.forge_class("gitea"), forge.Forgejo)

    def test_http_transport_never_prints_or_stores_the_token(self):
        with mock.patch.dict("os.environ", {"FORGEJO_TOKEN": "secret-value"}):
            t = forge.HttpTransport("codeberg.org")
            self.assertNotIn("secret-value", repr(t))
            self.assertNotIn("secret-value", str(vars(t)))

    def test_http_transport_guards_writes(self):
        t = forge.HttpTransport("codeberg.org")
        with self.assertRaises(forge.ForgeError):
            t.send("DELETE", "repos/o/r/issues/1")


class EpicMembersParsing(unittest.TestCase):
    def test_members_come_only_from_the_generated_task_list(self):
        body = fixture("forgejo_sync.json")["GET repos/example-org/search-service/issues/10"]["body"]
        self.assertEqual(blocks.epic_members(body), {"example-org/search-service#11", "example-org/search-service#12",
                                                     "example-org/search-service#99"})


if __name__ == "__main__":
    unittest.main()
