"""Replay recorded scenario actions offline, without an agent or Orca runtime."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from helpers import CLI, FIXTURES, example, fixture, issue
from roadmaplib import model
from test_render import parse
from test_sync import sync_roadmap


def run_cli(*args):
    return subprocess.run(
        [sys.executable, str(CLI), *map(str, args)],
        check=False,
        capture_output=True,
        text=True,
    )


class CoordinationReplay(unittest.TestCase):
    def test_area_reads_preserve_bytes_and_root_deltas_keep_intervening_history(self):
        scenario = fixture("coordination.json")
        pointer = scenario["pointer"]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / pointer["canonical"]
            path.parent.mkdir()
            model.save(path, sync_roadmap())
            initial = path.read_bytes()

            # Area observations run the real read-only command against recorded inputs.
            observed = []
            for delta in scenario["area_deltas"]:
                report = run_cli(
                    "sync",
                    path,
                    "--recorded",
                    FIXTURES / "gitlab_sync.json",
                    "--orca-json",
                    FIXTURES / "orca_tasks.json",
                    "--now",
                    "2026-11-18",
                )
                self.assertEqual(report.returncode, 0, report.stdout + report.stderr)
                self.assertIn("Drift", report.stdout)
                self.assertEqual(path.read_bytes(), initial)
                self.assertEqual(
                    issue(model.load(path), delta["issue"])["status"], delta["old"]
                )
                observed.append(delta)

            # This is the root's recorded action, followed by two area deltas
            # against an older read and one replay of the first delta.
            latest = model.load(path)
            root_event = {
                "id": "preview-restored",
                "date": "Nov 18",
                "text": "Root restored access for the review team.",
                "author": "claude",
            }
            latest["timeline"].append(root_event)
            model.save(path, latest)
            writers = [pointer["writer"]]

            for delta in [*observed, observed[0]]:
                current = model.load(path)
                if any(
                    e.get("id") == delta["event"]["id"] for e in current["timeline"]
                ):
                    continue
                item = issue(current, delta["issue"])
                self.assertEqual(item["status"], delta["old"])
                item["status"] = delta["new"]
                if "review_gate" in delta:
                    gate = delta["review_gate"]
                    self.assertIn(gate, item["gates"])
                    item["gates"][item["gates"].index(gate)] = {
                        "gate": gate,
                        "passed": True,
                        "evidence": delta["evidence"],
                    }
                current["timeline"].append(delta["event"])
                model.save(path, current)
                writers.append(pointer["writer"])

            result = run_cli("render", path)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            doc = parse(path.with_suffix(".html").read_text())
            for label in (
                "Ranking review passed",
                "Design approval waits on access",
                root_event["text"],
            ):
                self.assertIn(label, doc.text)
            final = model.load(path)

        self.assertEqual(writers, ["root", "root", "root"])
        self.assertEqual(
            [event["id"] for event in final["timeline"] if "id" in event],
            ["preview-restored", "ranking-review-passed", "design-approval-blocked"],
        )
        ranking = issue(final, "ranking-model")
        self.assertEqual(ranking["status"], "in_review")
        self.assertEqual(
            ranking["gates"][1],
            {
                "gate": "R",
                "passed": True,
                "evidence": "https://gitlab.example.com/acme/search/-/merge_requests/31#note_7",
            },
        )
        self.assertEqual(ranking["gates"][-1], "M")
        self.assertEqual(issue(final, "page-design")["status"], "blocked")
        self.assertEqual(issue(final, "page-design")["gates"][-1], "U")
        self.assertEqual(issue(final, "page-build")["status"], "to_do")

    def test_closed_forge_issue_stays_in_review_in_selective_replay(self):
        scenario = fixture("coordination.json")["closure"]
        issue_id, dependent_id = scenario["issue"], scenario["dependent"]
        data = sync_roadmap()
        issue(data, issue_id).update(
            status="in_review",
            gates=[*issue(example(), issue_id)["gates"][:2], "M", "U"],
        )
        issue(data, dependent_id)["status"] = "to_do"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "roadmap.json"
            model.save(path, data)
            initial = path.read_bytes()
            result = run_cli(
                "sync",
                path,
                "--recorded",
                FIXTURES / "gitlab_sync.json",
                "--no-orca",
                "--now",
                "2026-11-18",
                "--json",
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads(result.stdout)
            self.assertIn(
                (issue_id, "done"),
                [
                    (change["issue"], change["new"])
                    for change in report["status_changes"]
                ],
            )
            self.assertIn(
                (issue_id, "M"),
                [(tick["issue"], tick["gate"]) for tick in report["gate_ticks"]],
            )
            self.assertEqual(path.read_bytes(), initial)

            latest = model.load(path)
            for action in scenario["actions"]:
                if action == "record_merge_link":
                    merges = report["merge_requests"][issue_id]
                    self.assertEqual([mr["state"] for mr in merges], ["merged"])
                    issue(latest, issue_id)["merge_requests"] = merges
                    model.save(path, latest)
                else:
                    self.assertEqual(action, "hold_dispatch")
                    current = model.normalize(model.load(path))
                    self.assertFalse(
                        model.is_ready(
                            issue(current, dependent_id), model.issues_by_id(current)
                        )
                    )

            rendered = run_cli("render", path)
            self.assertEqual(rendered.returncode, 0, rendered.stdout + rendered.stderr)
            output = path.with_suffix(".html").read_text()
            final = model.load(path)

        self.assertEqual(scenario["release_evidence"], "Unknown")
        self.assertEqual(scenario["u_approval"], "Unknown")
        self.assertEqual(
            model.open_gates(issue(model.normalize(final), issue_id)), ["M", "U"]
        )
        self.assertIn(
            "https://gitlab.example.com/acme/search/-/merge_requests/30", output
        )
        self.assertEqual(issue(final, issue_id).pop("merge_requests"), merges)
        self.assertEqual(final, data)

    def test_worker_reports_require_timestamped_evidence_for_each_scope(self):
        for case in fixture("coordination.json")["activity"]:
            with self.subTest(case=case["name"]):
                tasks = {
                    (task["run"], task["id"]): task["status"]
                    for task in case["lifecycle"]
                }
                self.assertEqual(len(tasks), len(case["lifecycle"]))
                reports = {report["scope"]: report for report in case["reports"]}
                self.assertTrue(case["unread_runs"])
                self.assertEqual(reports["program"]["count"], "Unknown")
                for report in reports.values():
                    if report["observed_at"] is None:
                        self.assertNotIn("worker_states", report)
                        self.assertEqual(report["count"], "Unknown")
                    else:
                        self.assertIsNotNone(
                            datetime.fromisoformat(report["observed_at"]).tzinfo
                        )
                        self.assertEqual(
                            report["count"], report["worker_states"].count("working")
                        )

    def test_recorded_preview_actions_reuse_page_identity_and_respect_host(self):
        scenario = fixture("coordination.json")
        pointer = scenario["pointer"]
        for case in scenario["previews"]:
            with self.subTest(case=case["name"]):
                tabs = case["tabs"]
                route = case.get("initial_url", pointer["url"])
                for action in case["actions"]:
                    if action["operation"] == "unknown":
                        if route is None:
                            self.assertNotIn("private_route", case)
                            self.assertEqual(action["reason"], case["route_error"])
                        else:
                            self.assertNotEqual(case["host"], pointer["browser_host"])
                            self.assertIn(pointer["browser_host"], action["reason"])
                        continue

                    self.assertEqual(case["host"], pointer["browser_host"])
                    if action["operation"] == "record_route":
                        self.assertIsNone(route)
                        private_route = case["private_route"]
                        self.assertTrue(private_route["authorized"])
                        self.assertEqual(
                            action["browser_host"], private_route["verified_host"]
                        )
                        self.assertEqual(action["browser_host"], case["host"])
                        self.assertEqual(action["url"], private_route["url"])
                        route = action["url"]
                        continue

                    self.assertIsNotNone(route)
                    canonical_urls = {route, *pointer["aliases"]}
                    existing = [tab for tab in tabs if tab["url"] in canonical_urls]
                    if action["operation"] == "create":
                        self.assertEqual(existing, [])
                        self.assertEqual(
                            (action["split"], action["focus"]), ("right", "terminal")
                        )
                        tabs.append(
                            {
                                "id": action["id"],
                                "url": route,
                                "title": pointer["title"],
                                "adjacent": True,
                            }
                        )
                    else:
                        self.assertEqual(action["operation"], "reload")
                        self.assertEqual(len(existing), 1)
                        self.assertEqual(existing[0]["id"], action["id"])
                        self.assertEqual(existing[0]["title"], pointer["title"])
                        self.assertTrue(existing[0]["adjacent"])

                self.assertEqual([tab["id"] for tab in tabs], case["final_ids"])
                self.assertEqual(route, case.get("final_url", pointer["url"]))
