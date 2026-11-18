"""publish: refusals happen before any write, and pinning is checked per epic and cannot stop the run."""

from __future__ import annotations

import unittest

from fakeforge import FakeGitHub, github
from helpers import example, fixture, issue
from roadmaplib import forge, publish
from test_apply import REPO, fresh_forge

NUM = {"ranking": 10, "search-page": 13, "release-safety": 14}


class MissingProjectRefusedUpFront(unittest.TestCase):
    def roadmap(self):
        data = example()
        data["forge"] = {"kind": "github", "host": "github.com"}   # no default project
        for it in data["issues"]:
            if not it.get("ref") and it["id"] != "weekly-release":
                it["project"] = REPO
        for ep in data["epics"]:
            ep["ref"] = f"{REPO}#{NUM[ep['id']]}"
        return data

    def forge(self) -> FakeGitHub:
        fake = fresh_forge()
        fake.add_issue(REPO, 13, "Search page")
        fake.add_issue(REPO, 14, "Release safety")
        return fake

    def test_apply_refuses_before_writing_anything(self):
        fake = self.forge()
        for apply in (False, True):
            with self.assertRaises(publish.PublishRefused) as ctx:
                publish.publish(self.roadmap(), github(fake, project=None), apply=apply)
            self.assertIn("weekly-release", str(ctx.exception))
            self.assertEqual(fake.writes, [], "a refusal must come before the first forge write")

    def test_every_issue_with_a_project_is_not_refused(self):
        data = self.roadmap()
        issue(data, "weekly-release")["project"] = REPO
        report = publish.publish(data, github(self.forge(), project=None), apply=False)
        self.assertIsNone(report.failed)


class PinStub:
    """The forge methods publish calls, with scripted pin behavior (tests only)."""

    kind = "forgejo"
    host = "codeberg.org"
    project = "o/r"
    group = None
    epic_word = "parent issue"
    native_epics = False
    create_sets_epic = False
    pin_epics = True

    def __init__(self, slots, fail_pin_for=()):
        self.slots, self.fail_pin_for = list(slots), set(fail_pin_for)
        self.pinned, self.can_pin_calls, self.epic_writes = [], 0, []

    def get_epic(self, ref):
        n = int(ref.rsplit("#", 1)[1])
        return {"ref": ref, "url": None, "id": n, "number": n, "title": ref, "body": "", "pinned": False}

    def get_issue(self, ref):
        n = int(ref.rsplit("#", 1)[1])
        return {"ref": ref, "url": None, "id": n, "number": n, "title": ref, "body": "", "state": "open",
                "project": ref.rsplit("#", 1)[0]}

    def open_epics(self):
        return []

    def all_issues(self, project):
        return []

    def in_epic(self, issue, epic):
        return True

    def blocked_by(self, issue):
        return []

    def update_issue_body(self, issue, body):
        pass

    def update_epic_body(self, epic, body):
        self.epic_writes.append(epic["ref"])

    def add_blocked_by(self, issue, dep):
        pass

    def can_pin(self):
        self.can_pin_calls += 1
        return self.slots.pop(0) if self.slots else False

    def pin(self, epic):
        if epic["ref"] in self.fail_pin_for:
            raise forge.ForgeError(f"POST pin {epic['ref']} failed: HTTP 422")
        self.pinned.append(epic["ref"])


def pin_roadmap():
    data = example()
    data["forge"] = {"kind": "forgejo", "host": "codeberg.org", "project": "o/r", "pin_epics": True}
    for i, ep in enumerate(data["epics"], start=1):
        ep["ref"] = f"o/r#{100 + i}"
    for i, it in enumerate(data["issues"], start=1):
        it["ref"] = f"o/r#{i}"
        it.pop("project", None)
    return data


class PinningIsCheckedPerEpic(unittest.TestCase):
    def test_a_free_slot_is_rechecked_for_each_epic(self):
        stub = PinStub(slots=[True, False, False])
        report = publish.publish(pin_roadmap(), stub, apply=True)
        self.assertEqual(stub.can_pin_calls, 3)
        self.assertEqual(stub.pinned, ["o/r#101"])
        details = {a.target: a.detail for a in report.actions if a.kind == "pin-epic"}
        self.assertIn("no free pin slot", details["search-page"])
        self.assertIn("no free pin slot", details["release-safety"])

    def test_a_pin_failure_is_reported_and_the_epic_sections_are_still_written(self):
        stub = PinStub(slots=[True, True, True], fail_pin_for={"o/r#101"})
        report = publish.publish(pin_roadmap(), stub, apply=True)
        self.assertIsNone(report.failed)
        self.assertEqual(sorted(stub.epic_writes), ["o/r#101", "o/r#102", "o/r#103"])
        self.assertEqual(stub.pinned, ["o/r#102", "o/r#103"])
        self.assertTrue([a for a in report.actions if a.kind == "hand-fix" and "o/r#101" in a.detail
                         and "pin" in a.detail])

    def test_a_title_matched_epic_that_is_already_pinned_is_not_pinned_again(self):
        responses = dict(fixture("forgejo_publish.json"))
        listing = list(responses["GET repos/example-org/search-service/issues?state=all&type=issues"])
        listing.append({"id": 7030, "number": 30, "title": "Search page", "body": "", "state": "open",
                        "labels": [], "updated_at": "2026-11-16T10:00:00Z", "pin_order": 2,
                        "html_url": "https://codeberg.org/example-org/search-service/issues/30"})
        responses["GET repos/example-org/search-service/issues?state=all&type=issues"] = listing
        fg = forge.Forgejo(forge.RecordedTransport(responses), host="codeberg.org",
                           project="example-org/search-service")
        match = next(e for e in fg.open_epics() if e["number"] == 30)
        self.assertTrue(match["pinned"])


if __name__ == "__main__":
    unittest.main()
