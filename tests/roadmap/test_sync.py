"""sync: read-only status, gate evidence, and drift detection."""

from __future__ import annotations

import json
import subprocess
import sys
import re
import tempfile
import unittest
from pathlib import Path

from helpers import CLI, FIXTURES, fixture, issue
from roadmaplib import forge, orca, sync
from test_publish import NoWrites, gitlab_roadmap


def sync_roadmap() -> dict:
    data = gitlab_roadmap()
    issue(data, "ranking-check")["ref"] = "acme/search#13"
    issue(data, "page-design")["ref"] = "acme/search#20"
    # M not yet ticked locally: sync should tick it from the merged merge request.
    issue(data, "click-signals")["gates"] = ["D", "R", "M"]
    return data


def run_sync(data=None):
    fg = forge.GitLab(NoWrites(fixture("gitlab_sync.json")), host="gitlab.example.com",
                      project="acme/search", group="acme")
    tasks = orca.parse_tasks(fixture("orca_tasks.json"))
    return sync.sync(data or sync_roadmap(), fg, orca_tasks=tasks, stale_days=14, now="2026-11-17")


def drift(report, kind):
    return [d for d in report.drift if d.kind == kind]


class MentionedMergeRequestsDoNotMoveStatus(unittest.TestCase):
    """An open merge request that only mentions the issue is not work on it."""

    def run_with(self, description):
        responses = fixture("gitlab_sync.json")
        for key in ("GET projects/acme%2Fsearch/issues/12/related_merge_requests",
                    "GET projects/acme%2Fsearch/merge_requests/31"):
            body = responses[key]
            for mr in (body if isinstance(body, list) else [body]):
                mr["description"] = description
        fg = forge.GitLab(NoWrites(responses), host="gitlab.example.com", project="acme/search", group="acme")
        tasks = orca.parse_tasks(fixture("orca_tasks.json"))
        return sync.sync(sync_roadmap(), fg, orca_tasks=tasks, stale_days=14, now="2026-11-17")

    def test_a_mention_alone_leaves_the_status_alone(self):
        report = self.run_with("Related to #12, see the discussion there.")
        self.assertNotIn("ranking-model", {c.issue for c in report.status_changes})
        self.assertEqual(issue(report.roadmap, "ranking-model")["status"], "in_progress")
        self.assertIn("ranking-model", report.merge_requests)   # still reported as a related merge request

    def test_a_closing_merge_request_still_moves_it_to_review(self):
        report = self.run_with("Closes #12")
        self.assertEqual({c.issue: c.new for c in report.status_changes}["ranking-model"], "in_review")


class StatusFromForge(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = run_sync()

    def test_open_merge_request_moves_issue_to_in_review(self):
        changes = {c.issue: c for c in self.report.status_changes}
        self.assertEqual((changes["ranking-model"].old, changes["ranking-model"].new),
                         ("in_progress", "in_review"))

    def test_blocked_label_moves_issue_to_blocked(self):
        changes = {c.issue: c for c in self.report.status_changes}
        self.assertEqual(changes["ranking-check"].new, "blocked")

    def test_closed_done_issue_is_unchanged(self):
        self.assertNotIn("click-signals", {c.issue for c in self.report.status_changes})

    def test_no_activity_on_forge_does_not_move_status_backwards(self):
        # page-design is in review on the roadmap; the forge has no merge request yet.
        self.assertNotIn("page-design", {c.issue for c in self.report.status_changes})

    def test_merge_requests_and_pipelines_are_reported(self):
        mrs = self.report.merge_requests["ranking-model"]
        self.assertEqual(mrs[0]["ref"], "acme/search!31")
        self.assertEqual(mrs[0]["pipeline"], "success")
        self.assertIn("pipelines/77", mrs[0]["pipeline_url"])


class GateEvidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = run_sync()
        cls.ticks = {(t.issue, t.gate): t.evidence for t in cls.report.gate_ticks}

    def test_merged_merge_request_ticks_m_with_its_link(self):
        self.assertEqual(self.ticks[("click-signals", "M")],
                         "https://gitlab.example.com/acme/search/-/merge_requests/30")

    def test_a_lead_gate_ticked_on_the_forge_is_reported_not_ticked(self):
        self.assertNotIn(("page-design", "D"), self.ticks)
        self.assertIn(("lead-gate-ticked-on-forge", "page-design"), {(d.kind, d.target) for d in self.report.drift})

    def test_unticked_lines_and_open_merge_requests_tick_nothing(self):
        self.assertNotIn(("page-design", "U"), self.ticks)
        self.assertNotIn(("ranking-model", "M"), self.ticks)

    def test_ticks_land_in_the_updated_roadmap(self):
        gates = {g["gate"]: g for g in issue(self.report.roadmap, "click-signals")["gates"]}
        self.assertTrue(gates["M"]["passed"])
        self.assertIn("merge_requests/30", gates["M"]["evidence"])
        self.assertEqual(issue(self.report.roadmap, "ranking-model")["status"], "in_review")


class Drift(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = run_sync()

    def test_open_issue_in_an_epic_that_is_not_on_the_roadmap(self):
        found = drift(self.report, "unlisted-epic-issue")
        self.assertEqual([d.target for d in found], ["acme/search#99"])   # closed #98 is ignored

    def test_merge_request_with_no_roadmap_issue(self):
        found = [d.target for d in drift(self.report, "unlinked-merge-request")]
        self.assertEqual(found, ["acme/search!40"])   # !31 is related, !41 names page-build

    def test_orca_task_with_no_roadmap_issue(self):
        found = [d.target for d in drift(self.report, "unlinked-orca-task")]
        self.assertEqual(found, ["task_2"])           # completed task_4 is ignored

    def test_orca_task_started_before_dependencies_done(self):
        found = drift(self.report, "started-early")
        self.assertEqual([d.target for d in found], ["page-ranking"])
        self.assertIn("page-build", found[0].message)

    def test_issues_with_nothing_on_the_forge(self):
        found = {d.target for d in drift(self.report, "not-published")}
        self.assertEqual(found, {"page-build", "page-ranking", "release-checks", "weekly-release"})

    def test_issue_with_no_recent_activity(self):
        found = [d.target for d in drift(self.report, "no-recent-activity")]
        self.assertEqual(found, ["page-design"])

    def test_untouched_backlog_is_not_stale(self):
        """No activity is normal for work not started; only active work goes stale."""
        for status, stale in (("to_do", False), ("blocked", False), ("in_progress", True), ("in_review", True)):
            with self.subTest(status=status):
                data = sync_roadmap()
                issue(data, "page-design")["status"] = status
                found = [d.target for d in drift(run_sync(data), "no-recent-activity")]
                self.assertEqual(found, ["page-design"] if stale else [])

    def test_done_work_with_no_forge_issue_is_not_drift(self):
        """publish skips it on purpose, so it must not keep drift open forever."""
        data = sync_roadmap()
        issue(data, "weekly-release")["status"] = "done"
        self.assertNotIn("weekly-release", {d.target for d in drift(run_sync(data), "not-published")})

    def test_every_drift_kind_says_who_clears_it(self):
        source = Path(sync.__file__).read_text()
        kinds = set(re.findall(r'Drift\(\s*"([a-z-]+)"', source))
        self.assertTrue(kinds)
        self.assertEqual(kinds, set(sync.DRIFT_OWNER))
        self.assertLessEqual(sync.AGENT_DRIFT, kinds)
        self.assertNotIn("no-recent-activity", sync.AGENT_DRIFT)
        self.assertNotIn("lead-gate-ticked-on-forge", sync.AGENT_DRIFT)

    def test_report_text_names_each_section(self):
        text = self.report.text()
        for heading in ("Status changes", "Gates ticked", "Merge requests", "Drift"):
            self.assertIn(heading, text)
        self.assertIn("read-only", text)


class OrcaParsing(unittest.TestCase):
    def test_accepts_the_cli_envelope_or_a_bare_list(self):
        wrapped = orca.parse_tasks(fixture("orca_tasks.json"))
        bare = orca.parse_tasks(fixture("orca_tasks.json")["result"]["tasks"])
        self.assertEqual(wrapped, bare)
        self.assertEqual(len(wrapped), 4)


class SyncCommand(unittest.TestCase):
    def test_cli_report_and_write_touch_only_the_roadmap_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "roadmap.json"
            path.write_text(json.dumps(sync_roadmap()))
            base = [sys.executable, str(CLI), "sync", str(path), "--recorded",
                    str(FIXTURES / "gitlab_sync.json"), "--orca-json", str(FIXTURES / "orca_tasks.json"),
                    "--now", "2026-11-17"]
            before = path.read_text()
            out = subprocess.run(base, capture_output=True, text=True)
            self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
            self.assertIn("acme/search!40", out.stdout)
            self.assertEqual(path.read_text(), before)
            out = subprocess.run(base + ["--write"], capture_output=True, text=True)
            self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
            after = json.loads(path.read_text())
            self.assertEqual(issue(after, "ranking-model")["status"], "in_review")

    def test_json_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "roadmap.json"
            path.write_text(json.dumps(sync_roadmap()))
            out = subprocess.run([sys.executable, str(CLI), "sync", str(path), "--json", "--no-orca",
                                  "--recorded", str(FIXTURES / "gitlab_sync.json"), "--now", "2026-11-17"],
                                 capture_output=True, text=True)
            self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
            got = json.loads(out.stdout)
            self.assertIn("drift", got)
            self.assertFalse(any(d["kind"] == "unlinked-orca-task" for d in got["drift"]))


class MergeRequestsNamedInTheRoadmap(unittest.TestCase):
    """A roadmap issue that names a merge request in its text accounts for it."""

    def run_with(self, detail):
        data = sync_roadmap()
        data["forge"]["projects"] = ["acme/web"]
        issue(data, "page-build")["detail"] = detail
        responses = dict(fixture("gitlab_sync.json"))
        mr = fixture("gitlab_sync.json")["GET projects/acme%2Fsearch/merge_requests?state=opened"][1]
        responses["GET projects/acme%2Fweb/merge_requests?state=opened"] = [
            dict(mr, iid=7, title="Web change", references={"full": "acme/web!7"}),
            dict(mr, iid=8, title="Other web change", references={"full": "acme/web!8"})]
        fg = forge.GitLab(NoWrites(responses), host="h", project="acme/search", group="acme")
        report = sync.sync(data, fg, orca_tasks=[], now="2026-11-17")
        return {d.target for d in report.drift if d.kind == "unlinked-merge-request"}

    def test_bang_number_means_the_default_project(self):
        found = self.run_with("Follow-up to !40")
        self.assertNotIn("acme/search!40", found)
        self.assertIn("acme/web!7", found)

    def test_project_name_before_the_number_means_that_project(self):
        found = self.run_with("web !7 ships with search !40")
        self.assertNotIn("acme/web!7", found)
        self.assertNotIn("acme/search!40", found)
        self.assertIn("acme/web!8", found)

    def test_full_reference_and_url(self):
        found = self.run_with("See acme/web!8 and https://gitlab.example.com/acme/web/-/merge_requests/7")
        self.assertNotIn("acme/web!8", found)
        self.assertNotIn("acme/web!7", found)


if __name__ == "__main__":
    unittest.main()
