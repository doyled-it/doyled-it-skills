"""publish: dry run against recorded forge responses, plus one recorded apply."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import CLI, FIXTURES, example, fixture, issue
from roadmaplib import forge, publish


def gitlab_roadmap() -> dict:
    """The example roadmap, tracked on a GitLab group instead of GitHub."""
    data = example()
    data["forge"] = {"kind": "gitlab", "host": "gitlab.example.com", "project": "acme/search", "group": "acme"}
    data["epics"][0]["ref"] = "acme&10"
    data["epics"][0]["url"] = "https://gitlab.example.com/groups/acme/-/epics/10"
    issue(data, "click-signals")["ref"] = "acme/search#11"
    issue(data, "ranking-model")["ref"] = "acme/search#12"
    return data


class NoWrites(forge.RecordedTransport):
    def send(self, method, path, body=None, allow_close=False):
        raise AssertionError(f"dry run tried to write: {method} {path}")


def kinds(report, kind):
    return [a for a in report.actions if a.kind == kind]


class GitLabDryRun(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fg = forge.GitLab(NoWrites(fixture("gitlab_publish.json")), host="gitlab.example.com",
                          project="acme/search", group="acme")
        cls.report = publish.publish(gitlab_roadmap(), fg, apply=False)

    def test_existing_epic_is_linked_and_new_epics_are_created(self):
        self.assertEqual([a.target for a in kinds(self.report, "link-epic")], ["ranking", "search-page"])
        self.assertEqual([a.target for a in kinds(self.report, "create-epic")], ["release-safety"])

    def test_open_epic_with_the_same_name_is_linked_instead_of_duplicated(self):
        page = next(a for a in kinds(self.report, "link-epic") if a.target == "search-page")
        self.assertIn("acme&11", page.detail)
        self.assertIn("same title", page.detail)
        update = next(a for a in kinds(self.report, "update-epic") if a.target == "search-page")
        self.assertTrue(update.body.startswith("Hand-written plan."))

    def test_named_issues_are_linked_not_duplicated(self):
        linked = {a.target for a in kinds(self.report, "link-issue")}
        self.assertTrue({"click-signals", "ranking-model"} <= linked)
        created = {a.target for a in kinds(self.report, "create-issue")}
        self.assertNotIn("click-signals", created)
        self.assertNotIn("ranking-model", created)

    def test_open_issue_with_the_same_title_is_linked_instead_of_duplicated(self):
        page = [a for a in kinds(self.report, "link-issue") if a.target == "page-design"]
        self.assertEqual(len(page), 1)
        self.assertIn("acme/search#20", page[0].detail)
        self.assertIn("same title", page[0].detail)

    def test_remaining_issues_are_created(self):
        created = {a.target for a in kinds(self.report, "create-issue")}
        self.assertEqual(created, {"ranking-check", "page-build", "page-ranking", "release-checks",
                                   "weekly-release"})

    def test_blocked_by_links_skip_existing_ones(self):
        pairs = {(a.target, a.detail.split()[-1]) for a in kinds(self.report, "add-blocked-by")}
        self.assertNotIn(("ranking-model", "click-signals"), pairs)
        self.assertIn(("ranking-check", "ranking-model"), pairs)
        self.assertIn(("page-ranking", "ranking-check"), pairs)
        self.assertIn(("weekly-release", "click-signals"), pairs)
        self.assertEqual(len(pairs), 6)

    def test_epic_membership(self):
        added = {a.target for a in kinds(self.report, "add-to-epic")}
        self.assertIn("ranking-model", added)      # open on the forge with no epic
        self.assertIn("page-design", added)        # linked by title, not yet in its epic
        self.assertNotIn("click-signals", added)   # already in the epic

    def test_gate_checklists_are_written_and_hand_text_is_kept(self):
        updates = {a.target: a for a in kinds(self.report, "update-issue")}
        self.assertIn("page-design", updates)
        body = updates["page-design"].body
        block = body.split("<!-- roadmap:start -->", 1)[1]
        self.assertIn("- [ ] D:", block)           # a checkbox outside the block, and a lead gate, tick nothing
        self.assertIn("- [ ] U:", block)
        self.assertTrue(body.startswith("Layout notes.\n\n- [x] D: Design agreed"))   # hand text kept as is

    def test_dry_run_does_not_change_the_roadmap(self):
        self.assertFalse(self.report.applied)
        self.assertIn("Dry run", self.report.text())
        self.assertIn("--apply", self.report.text())


class GitHubDryRun(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fg = forge.GitHub(NoWrites(fixture("github_publish.json")), host="github.com",
                          project="example-org/search-service")
        cls.report = publish.publish(example(), fg, apply=False)

    def test_pull_requests_are_not_mistaken_for_issues(self):
        created = {a.target for a in kinds(self.report, "create-issue")}
        self.assertIn("page-build", created)       # a pull request has that title, not an issue

    def test_github_epics_are_parent_issues(self):
        self.assertEqual([a.target for a in kinds(self.report, "link-epic")], ["ranking"])
        create = kinds(self.report, "create-epic")
        self.assertTrue(all("parent issue" in a.detail for a in create))
        added = {a.target for a in kinds(self.report, "add-to-epic")}
        self.assertIn("ranking-model", added)
        self.assertNotIn("click-signals", added)

    def test_blocked_by_uses_issue_dependencies(self):
        pairs = {(a.target, a.detail.split()[-1]) for a in kinds(self.report, "add-blocked-by")}
        self.assertNotIn(("ranking-model", "click-signals"), pairs)
        self.assertIn(("page-build", "page-design"), pairs)


class Refusals(unittest.TestCase):
    def test_draft_roadmap_is_refused(self):
        data = gitlab_roadmap()
        data["agreed"] = False
        fg = forge.GitLab(NoWrites({}), host="h", project="acme/search", group="acme")
        with self.assertRaises(publish.PublishRefused) as ctx:
            publish.publish(data, fg, apply=False)
        self.assertIn("agreed", str(ctx.exception))

    def test_gitlab_epic_with_no_group_is_refused_by_the_dry_run_too(self):
        # Found live: the dry run listed "create epic" and exited 0, then --apply
        # stopped at the first epic. GitLab epics live in a group, so both refuse
        # before any forge call.
        data = gitlab_roadmap()
        del data["forge"]["group"]
        for apply in (False, True):
            fg = forge.GitLab(NoWrites({}), host="h", project="acme/search", group=None)
            with self.assertRaises(publish.PublishRefused) as ctx:
                publish.publish(data, fg, apply=apply)
            self.assertIn('"group"', str(ctx.exception))
            self.assertIn("search-page, release-safety", str(ctx.exception))
            self.assertNotIn("ranking", str(ctx.exception))  # it names its epic in "ref"

    def test_gitlab_with_no_group_is_fine_when_every_epic_has_a_ref(self):
        data = gitlab_roadmap()
        del data["forge"]["group"]
        data["epics"] = data["epics"][:1]
        for it in data["issues"]:
            it["epic"] = data["epics"][0]["id"]
        fg = forge.GitLab(NoWrites(fixture("gitlab_publish.json")), host="gitlab.example.com",
                          project="acme/search", group=None)
        report = publish.publish(data, fg, apply=False)
        self.assertIsNone(report.failed)
        self.assertEqual(kinds(report, "create-epic"), [])

    def test_roadmap_with_errors_is_refused(self):
        data = gitlab_roadmap()
        issue(data, "page-build")["depends_on"] = ["ghost"]
        fg = forge.GitLab(NoWrites({}), host="h", project="acme/search", group="acme")
        with self.assertRaises(publish.PublishRefused):
            publish.publish(data, fg, apply=False)

    def test_transport_refuses_deletes_and_closes(self):
        guard = forge.WriteGuard()
        with self.assertRaises(forge.ForgeError):
            guard.check("DELETE", "projects/1/issues/2", None)
        with self.assertRaises(forge.ForgeError):
            guard.check("PUT", "projects/1/issues/2", {"state_event": "close"})
        with self.assertRaises(forge.ForgeError):
            guard.check("PATCH", "repos/o/r/issues/2", {"state": "closed"})
        guard.check("POST", "projects/1/issues", {"title": "fine"})


class Recorder(forge.RecordedTransport):
    def __init__(self, responses):
        super().__init__(responses)
        self.calls = []

    def send(self, method, path, body=None, allow_close=False):
        forge.WriteGuard().check(method, path, body, allow_close=allow_close)
        self.calls.append((method, path, body))
        return self.responses.get(f"{method} {path}", {})


class GitLabApply(unittest.TestCase):
    def test_apply_creates_links_and_writes_refs_back(self):
        data = gitlab_roadmap()
        data["epics"] = data["epics"][:1]
        data["issues"] = [issue(data, "click-signals"), issue(data, "ranking-model")]
        del issue(data, "ranking-model")["ref"]
        responses = dict(fixture("gitlab_publish.json"))
        responses["GET projects/acme%2Fsearch/issues?state=all"] = []
        responses["POST projects/acme%2Fsearch/issues"] = {
            "id": 2021, "iid": 21, "project_id": 7, "title": "Rank results by open rate", "description": "",
            "state": "opened", "labels": [], "references": {"full": "acme/search#21"},
            "web_url": "https://gitlab.example.com/acme/search/-/issues/21"}
        rec = Recorder(responses)
        fg = forge.GitLab(rec, host="gitlab.example.com", project="acme/search", group="acme")
        report = publish.publish(data, fg, apply=True)
        self.assertTrue(report.applied)
        got = issue(report.roadmap, "ranking-model")
        self.assertEqual(got["ref"], "acme/search#21")
        self.assertEqual(got["url"], "https://gitlab.example.com/acme/search/-/issues/21")
        methods = [(m, p) for m, p, _ in rec.calls]
        self.assertIn(("POST", "projects/acme%2Fsearch/issues"), methods)
        self.assertIn(("POST", "projects/acme%2Fsearch/issues/21/links"), methods)
        create = next(b for m, p, b in rec.calls if p == "projects/acme%2Fsearch/issues")
        self.assertEqual(create["epic_id"], 510)
        link = next(b for m, p, b in rec.calls if p.endswith("/21/links"))
        self.assertEqual(link["link_type"], "is_blocked_by")
        self.assertEqual(link["target_issue_iid"], 11)
        self.assertTrue(all(m != "DELETE" for m, _ in methods))


class PublishCommand(unittest.TestCase):
    def test_cli_dry_run_with_recorded_responses(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "roadmap.json"
            path.write_text(json.dumps(gitlab_roadmap()))
            before = path.read_text()
            out = subprocess.run([sys.executable, str(CLI), "publish", str(path), "--recorded",
                                  str(FIXTURES / "gitlab_publish.json")], capture_output=True, text=True)
            self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
            self.assertIn("Dry run", out.stdout)
            self.assertIn("create issue", out.stdout)
            self.assertEqual(path.read_text(), before)


if __name__ == "__main__":
    unittest.main()
