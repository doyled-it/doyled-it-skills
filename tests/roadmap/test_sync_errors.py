"""sync: done-but-open drift, forge errors, refusals before writes, stale records, Orca states."""

from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from helpers import CLI, FIXTURES, fixture, issue
from roadmaplib import cli, forge, orca, sync
from test_publish import NoWrites, Recorder
from test_sync import run_sync, sync_roadmap

ISSUE12 = "GET projects/acme%2Fsearch/issues/12"


class Flaky(NoWrites):
    """Recorded responses, with chosen reads failing as a rate limit or server error would."""

    def __init__(self, responses, failing):
        super().__init__(responses)
        self.failing = failing

    def get(self, path):
        if f"GET {path}" in self.failing:
            raise forge.ForgeError(f"GET {path} failed: HTTP 502")
        return super().get(path)


def gitlab(transport):
    return forge.GitLab(transport, host="gitlab.example.com", project="acme/search", group="acme")


class DoneButOpen(unittest.TestCase):
    def test_done_on_the_roadmap_and_open_on_the_forge_is_drift(self):
        data = sync_roadmap()
        issue(data, "page-design")["status"] = "done"    # forge #20 is open, with no merge request
        found = [d.target for d in run_sync(data).drift if d.kind == "done-but-open"]
        self.assertEqual(found, ["page-design"])

    def test_done_and_closed_is_not_drift(self):
        self.assertFalse([d for d in run_sync().drift if d.kind == "done-but-open"])


class ForgeErrors(unittest.TestCase):
    def test_a_server_error_is_reported_as_an_error_not_as_a_missing_issue(self):
        fg = gitlab(Flaky(fixture("gitlab_sync.json"), {ISSUE12}))
        report = sync.sync(sync_roadmap(), fg, orca_tasks=[], now="2026-11-17")
        self.assertNotIn("ranking-model", [d.target for d in report.drift if d.kind == "missing-on-forge"])
        self.assertTrue(any("ranking-model" in e and "HTTP 502" in e for e in report.errors))
        self.assertIn("Incomplete", report.text())

    def test_a_missing_merge_request_list_does_not_crash(self):
        responses = dict(fixture("gitlab_sync.json"))
        del responses["GET projects/acme%2Fsearch/issues/12/related_merge_requests"]
        report = sync.sync(sync_roadmap(), gitlab(NoWrites(responses)), orca_tasks=[], now="2026-11-17")
        self.assertTrue(any("ranking-model" in e for e in report.errors))

    def test_a_failed_epic_write_is_reported(self):
        responses = dict(fixture("gitlab_sync.json"))
        responses["GET groups/acme/epics/10"] = {"id": 510, "iid": 10, "title": "Better ranking",
                                                 "description": "Hand text.", "web_url": "https://x.example/e"}

        class Refusing(Recorder):
            def send(self, method, path, body=None):
                raise forge.ForgeError(f"{method} {path} failed: HTTP 403")

        report = sync.sync(sync_roadmap(), gitlab(Refusing(responses)), orca_tasks=[], now="2026-11-17",
                           update_epics=True)
        self.assertTrue(any("acme&10" in e and "HTTP 403" in e for e in report.write_errors))
        self.assertEqual(report.errors, [])

    def test_cli_exits_1_and_saves_nothing_when_reads_failed(self):
        fg = gitlab(Flaky(fixture("gitlab_sync.json"), {ISSUE12}))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "roadmap.json"
            path.write_text(json.dumps(sync_roadmap()))
            before = path.read_text()
            out = io.StringIO()
            with mock.patch.object(forge, "from_args", return_value=fg), redirect_stdout(out):
                code = cli.main(["sync", str(path), "--write", "--no-orca", "--now", "2026-11-17"])
            self.assertEqual(code, 1)
            self.assertEqual(path.read_text(), before)
            self.assertIn("HTTP 502", out.getvalue())


EPIC10 = {"id": 510, "iid": 10, "title": "Better ranking", "description": "Hand text.",
          "web_url": "https://gitlab.example.com/groups/acme/-/epics/10"}
EPIC11 = {"id": 511, "iid": 11, "title": "Search page", "description": "Plan.",
          "web_url": "https://gitlab.example.com/groups/acme/-/epics/11"}


class Writer(Recorder):
    """Recorded reads (some failing) and recorded writes (one failing, counted from 1)."""

    def __init__(self, responses, failing=(), fail_write=None):
        super().__init__(responses)
        self.failing, self.fail_write = set(failing), fail_write

    def get(self, path):
        if f"GET {path}" in self.failing:
            raise forge.ForgeError(f"GET {path} failed: HTTP 502")
        return super().get(path)

    def send(self, method, path, body=None, allow_close=False):
        if self.fail_write is not None and len(self.calls) + 1 == self.fail_write:
            raise forge.ForgeError(f"{method} {path} failed: HTTP 403")
        return super().send(method, path, body, allow_close)


def two_epics() -> tuple[dict, dict]:
    data = sync_roadmap()
    data["epics"][1]["ref"] = "acme&11"
    responses = dict(fixture("gitlab_sync.json"))
    responses["GET groups/acme/epics/10"] = EPIC10
    responses["GET groups/acme/epics/11"] = EPIC11
    responses["GET groups/acme/epics/11/issues"] = []
    return data, responses


class EpicWritesComeLast(unittest.TestCase):
    """Epics are rewritten only after every read succeeded, so forge and roadmap.json agree."""

    def run_sync(self, transport, data):
        return sync.sync(data, gitlab(transport), orca_tasks=[], now="2026-11-17", update_epics=True)

    def test_no_epic_write_when_an_issue_read_failed(self):
        data, responses = two_epics()
        rec = Writer(responses, failing={ISSUE12})
        report = self.run_sync(rec, data)
        self.assertEqual(rec.calls, [])
        self.assertTrue(any("did not update epic acme&10" in n for n in report.notes))

    def test_no_epic_write_when_open_merge_requests_cannot_be_read(self):
        data, responses = two_epics()
        rec = Writer(responses, failing={"GET projects/acme%2Fsearch/merge_requests?state=opened"})
        report = self.run_sync(rec, data)
        self.assertEqual(rec.calls, [])
        self.assertTrue(report.errors)

    def test_a_failed_epic_write_still_saves_roadmap_json(self):
        """The first epic now shows the synced status, so roadmap.json must too."""
        data, responses = two_epics()
        rec = Writer(responses, fail_write=2)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "roadmap.json"
            path.write_text(json.dumps(data))
            out = io.StringIO()
            with mock.patch.object(forge, "from_args", return_value=gitlab(rec)), redirect_stdout(out):
                code = cli.main(["sync", str(path), "--write", "--update-epics", "--no-orca", "--now", "2026-11-17"])
            saved = json.loads(path.read_text())
        self.assertEqual(code, 1, out.getvalue())
        self.assertEqual(len(rec.calls), 1)
        self.assertEqual(issue(saved, "ranking-model")["status"], "in_review")
        self.assertIn("HTTP 403", out.getvalue())


class RefusalsBeforeWrites(unittest.TestCase):
    def test_update_epics_refuses_a_draft(self):
        data = sync_roadmap()
        data["agreed"] = False
        rec = Recorder(fixture("gitlab_sync.json"))
        with self.assertRaises(sync.SyncRefused):
            sync.sync(data, gitlab(rec), orca_tasks=[], now="2026-11-17", update_epics=True)
        self.assertEqual(rec.calls, [])

    def test_a_roadmap_with_structural_errors_is_refused_not_crashed(self):
        data = sync_roadmap()
        issue(data, "page-ranking")["depends_on"].append("ghost")
        with self.assertRaises(sync.SyncRefused) as ctx:
            sync.sync(data, gitlab(NoWrites(fixture("gitlab_sync.json"))), orca_tasks=orca.parse_tasks(
                fixture("orca_tasks.json")), now="2026-11-17")
        self.assertIn("ghost", str(ctx.exception))

    def test_update_epics_needs_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "roadmap.json"
            path.write_text(json.dumps(sync_roadmap()))
            res = subprocess.run([sys.executable, str(CLI), "sync", str(path), "--update-epics", "--no-orca",
                                  "--recorded", str(FIXTURES / "gitlab_sync.json")], capture_output=True, text=True)
        self.assertEqual(res.returncode, 2, res.stdout + res.stderr)
        self.assertIn("--write", res.stdout + res.stderr)

    def test_an_invalid_now_is_a_clear_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "roadmap.json"
            path.write_text(json.dumps(sync_roadmap()))
            res = subprocess.run([sys.executable, str(CLI), "sync", str(path), "--now", "next tuesday", "--no-orca",
                                  "--recorded", str(FIXTURES / "gitlab_sync.json")], capture_output=True, text=True)
        self.assertEqual(res.returncode, 2)
        self.assertNotIn("Traceback", res.stderr)
        self.assertIn("--now", res.stderr)


class StaleMergeRequestRecords(unittest.TestCase):
    def test_merge_requests_that_are_gone_are_removed_on_write(self):
        data = sync_roadmap()
        issue(data, "page-design")["merge_requests"] = [{"ref": "acme/search!9", "url": "https://x.example/9",
                                                          "state": "open"}]
        report = run_sync(data)
        self.assertNotIn("merge_requests", issue(report.roadmap, "page-design"))
        self.assertTrue(report.changed)


class OrcaStates(unittest.TestCase):
    def tasks(self, status):
        return [{"id": "task_9", "status": status, "title": "page-ranking: wire the switch"}]

    def test_queued_tasks_are_not_started(self):
        for status in ("ready", "blocked", "pending", "queued"):
            with self.subTest(status=status):
                report = sync.sync(sync_roadmap(), gitlab(NoWrites(fixture("gitlab_sync.json"))),
                                   orca_tasks=self.tasks(status), now="2026-11-17")
                self.assertFalse([d for d in report.drift if d.kind == "started-early"])

    def test_dispatched_and_running_tasks_are_started(self):
        for status in ("dispatched", "running"):
            with self.subTest(status=status):
                report = sync.sync(sync_roadmap(), gitlab(NoWrites(fixture("gitlab_sync.json"))),
                                   orca_tasks=self.tasks(status), now="2026-11-17")
                self.assertTrue([d for d in report.drift if d.kind == "started-early"])

    def test_orca_failure_message_is_plain_text(self):
        failed = mock.Mock(returncode=1, stdout="", stderr="line one\nerror: run not found\n")
        with mock.patch("shutil.which", return_value="/usr/bin/orca"), mock.patch("subprocess.run",
                                                                                   return_value=failed):
            with self.assertRaises(RuntimeError) as ctx:
                orca.read_run("run_1")
        self.assertEqual(str(ctx.exception), "error: run not found")


if __name__ == "__main__":
    unittest.main()
