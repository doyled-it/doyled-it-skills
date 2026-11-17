"""publish --apply against a stateful fake GitHub: idempotency, failures, done work, collisions."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from fakeforge import FakeGitHub, github
from helpers import example, issue
from roadmaplib import cli, forge, publish, validate

REPO = "example-org/search-service"


def fresh_forge() -> FakeGitHub:
    """The forge the example roadmap names: epic #10, issues #11 (closed) and #12."""
    fake = FakeGitHub()
    fake.add_issue(REPO, 10, "Better ranking", "Ranking work.")
    fake.add_issue(REPO, 11, "Record which results people open", "Anonymous counts.", state="closed")
    fake.add_issue(REPO, 12, "Rank results by open rate", "Blend.")
    fake.sub_issues[(REPO, 10)] = [fake.issues[(REPO, 11)]["id"]]
    fake.blocked[(REPO, 12)] = [fake.issues[(REPO, 11)]["id"]]
    return fake


class ApplyTwice(unittest.TestCase):
    def test_second_apply_writes_nothing_and_creates_no_duplicates(self):
        fake = fresh_forge()
        first = publish.publish(example(), github(fake), apply=True)
        n_first = len(fake.writes)
        self.assertGreater(n_first, 10)
        titles = fake.titles(REPO)
        second = publish.publish(first.roadmap, github(fake), apply=True)
        self.assertEqual(fake.writes[n_first:], [], [a.kind for a in second.actions])
        self.assertEqual(fake.titles(REPO), titles)
        self.assertEqual(len(titles), len(set(titles)))

    def test_rerun_with_the_unsaved_roadmap_after_a_failure_creates_no_duplicates(self):
        fake = fresh_forge()
        fake.fail_on_write = 6
        report = publish.publish(example(), github(fake), apply=True)
        self.assertIn("HTTP 403", report.failed)
        self.assertIn("Stopped", report.text())
        fake.fail_on_write = None
        publish.publish(example(), github(fake), apply=True)
        titles = fake.titles(REPO)
        self.assertEqual(len(titles), len(set(titles)))


class FailedApplyKeepsItsRecord(unittest.TestCase):
    def test_cli_prints_the_partial_report_and_saves_the_links_made(self):
        fake = fresh_forge()
        fake.fail_on_write = 6
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "roadmap.json"
            path.write_text(json.dumps(example()))
            out = io.StringIO()
            with mock.patch.object(forge, "from_args", return_value=github(fake)), redirect_stdout(out):
                code = cli.main(["publish", str(path), "--apply"])
            saved = json.loads(path.read_text())
        self.assertEqual(code, 2)
        self.assertIn("HTTP 403", out.getvalue())
        self.assertIn("create epic", out.getvalue())
        created = [i for i in saved["epics"] + saved["issues"] if i.get("ref") and i["id"] not in
                   ("ranking", "click-signals", "ranking-model")]
        self.assertTrue(created, "refs of what was created before the failure are saved")


class DoneWork(unittest.TestCase):
    def test_done_issue_with_no_ref_links_a_closed_issue_with_its_title(self):
        fake = fresh_forge()
        fake.add_issue(REPO, 13, "Design the results page", state="closed")
        data = example()
        issue(data, "page-design")["status"] = "done"
        issue(data, "page-design")["gates"] = []
        report = publish.publish(data, github(fake), apply=True)
        self.assertEqual(issue(report.roadmap, "page-design")["ref"], f"{REPO}#13")
        self.assertEqual(fake.titles(REPO).count("Design the results page"), 1)

    def test_unfinished_work_is_never_linked_to_an_old_closed_issue(self):
        """A closed issue with the same title is earlier work; linking it would make sync mark this Done."""
        fake = fresh_forge()
        fake.add_issue(REPO, 1, "Release every Tuesday", "From last year.", state="closed")
        for status in ("to_do", "in_progress"):
            with self.subTest(status=status):
                data = example()
                issue(data, "weekly-release")["status"] = status
                report = publish.publish(data, github(fake), apply=False)
                kinds = {a.kind for a in report.actions if a.target == "weekly-release"}
                self.assertNotIn("link-issue", kinds)
                self.assertIn("create-issue", kinds)
                create = next(a for a in report.actions if a.kind == "create-issue" and a.target == "weekly-release")
                self.assertIn(f"{REPO}#1", create.detail)
                self.assertNotIn("ref", issue(report.roadmap, "weekly-release"))

    def test_done_issue_with_nothing_on_the_forge_is_not_created(self):
        fake = fresh_forge()
        data = example()
        issue(data, "page-design")["status"] = "done"
        issue(data, "page-design")["gates"] = []
        report = publish.publish(data, github(fake), apply=True)
        self.assertNotIn("Design the results page", fake.titles(REPO))
        self.assertIn("page-design", [a.target for a in report.actions if a.kind == "skip-issue"])


class TitleCollisions(unittest.TestCase):
    def test_validate_rejects_duplicate_titles_and_refs(self):
        data = example()
        issue(data, "ranking-check")["title"] = issue(data, "ranking-model")["title"]
        issue(data, "page-build")["title"] = "better ranking"   # same as an epic name
        issue(data, "page-design")["ref"] = issue(data, "ranking-model")["ref"]
        found = {f.code for f in validate.errors(validate.check(data))}
        self.assertIn("duplicate-title", found)
        self.assertIn("duplicate-ref", found)

    def test_a_forge_issue_is_linked_to_one_roadmap_item_only(self):
        fake = fresh_forge()
        fake.issues[(REPO, 12)]["title"] = "New search page"    # named by ranking-model, retitled like an epic
        report = publish.publish(example(), github(fake), apply=False)
        epic = next(a for a in report.actions if a.target == "search-page" and "epic" in a.kind)
        self.assertEqual(epic.kind, "create-epic")
        linked = [a.detail.split()[0] for a in report.actions if a.kind in ("link-epic", "link-issue")]
        self.assertEqual(len(linked), len(set(linked)), linked)


class CrossRepository(unittest.TestCase):
    def test_existing_cross_repository_dependency_is_found_by_id(self):
        fake = fresh_forge()
        other = fake.add_issue("example-org/data", 5, "Collect the click log")
        fake.blocked[(REPO, 12)].append(other["id"])
        data = example()
        data["issues"].append({"id": "click-log", "title": "Collect the click log", "epic": "ranking",
                               "status": "done", "ref": "example-org/data#5",
                               "url": "https://github.com/example-org/data/issues/5"})
        issue(data, "ranking-model")["depends_on"].append("click-log")
        fake.sub_issues[(REPO, 10)].append(other["id"])
        report = publish.publish(data, github(fake), apply=False)
        self.assertNotIn("ranking-model", [a.target for a in report.actions if a.kind == "add-blocked-by"])
        self.assertNotIn("click-log", [a.target for a in report.actions if a.kind == "add-to-epic"])


if __name__ == "__main__":
    unittest.main()
