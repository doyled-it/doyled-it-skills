"""Offline multi-run collection, sync reporting and CLI compatibility."""

from __future__ import annotations

import io
import json
import subprocess
import tempfile
import unittest
from argparse import Namespace
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from helpers import FIXTURES, fixture
from roadmaplib import cli, forge, orca, render, sync
from test_drift_issue import fresh_forge, github, quiet
from test_ownership import owned_roadmap
from test_publish import NoWrites
from test_sync import sync_roadmap


def task(title, *, status="running", **metadata):
    return {"id": "task_same", "title": title, "status": status, **metadata}


def collect_recorded(data, payload, **args):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "orca.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return orca.tasks_from_args(data, Namespace(orca_json=path, **args))


def report_for(data, tasks):
    fg = forge.GitLab(
        NoWrites(fixture("gitlab_sync.json")), host="gitlab.example.com", project="acme/search", group="acme"
    )
    return sync.sync(data, fg, orca_tasks=tasks, now="2026-11-17")


OBSERVED = "2026-11-19T19:15:41.234Z"


def dispatched(task_id, dispatch):
    return {"id": task_id, "title": "page-ranking: run the worker", "status": "dispatched", "dispatchId": dispatch}


def worker(task_id, dispatch, activity, **extra):
    return {
        "ok": True,
        "result": {
            "dispatchId": dispatch,
            "taskId": task_id,
            "runId": "run_storage",
            "state": "ready",
            "stage": "input_accepted",
            "liveness": "live",
            "activity": activity,
            **extra,
        },
    }


class Collection(unittest.TestCase):
    def test_each_configured_run_is_read_once_and_shared_owners_keep_their_parent(self):
        data = owned_roadmap()
        coordinators = data["orchestration"]["coordinators"]
        coordinators["partner"] = {"run": "run_storage", "parent": "search", "role": "worker"}
        data["orca"]["run"] = "run_legacy"
        source_task = task(
            "Document the export",
            run="source-run",
            owner="task owner",
            parent="parent task",
            extra={"detail": "preserve"},
        )
        calls = []

        def command(argv, **kwargs):
            calls.append(argv)
            payload = {"ok": True, "result": {"tasks": [source_task] if argv[-2] == "run_storage" else []}}
            return subprocess.CompletedProcess(argv, 0, stdout=json.dumps(payload), stderr="")

        alias = "local-orca"
        executable = "/fake/Orca tools/orca-wrapper"
        with (
            mock.patch.dict("os.environ", {"ORCA_CLI_COMMAND": alias}, clear=True),
            mock.patch("shutil.which", return_value=executable) as resolve,
            mock.patch("subprocess.run", side_effect=command),
        ):
            tasks = orca.tasks_from_args(data, Namespace())
        resolve.assert_called_once_with(alias)
        self.assertCountEqual(
            calls,
            [
                [executable, "orchestration", "task-list", "--run", run, "--json"]
                for run in ("run_root", "run_storage", "run_search", "run_release", "run_legacy")
            ],
        )
        self.assertIsInstance(tasks, list)
        self.assertTrue(getattr(tasks, "complete", False))
        self.assertEqual(tasks, [source_task])
        self.assertEqual(tasks[0].source_run, "run_storage")
        self.assertEqual(tasks[0].run_owners, {"storage": coordinators["storage"], "partner": coordinators["partner"]})
        self.assertIn(alias, "\n".join(tasks.notes))
        self.assertIn(executable, "\n".join(tasks.notes))

    def test_explicit_run_overrides_configured_live_runs(self):
        with mock.patch("shutil.which", return_value="/fake/orca"), mock.patch("subprocess.run") as run:
            run.return_value = subprocess.CompletedProcess([], 0, stdout="[]", stderr="")
            tasks = orca.tasks_from_args(owned_roadmap(), Namespace(orca_run="run_explicit"))
        self.assertEqual(tasks, [])
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[0][-3:], ["--run", "run_explicit", "--json"])

    def test_successful_override_cannot_certify_unread_runs(self):
        data = owned_roadmap()
        with mock.patch("shutil.which", return_value="/fake/orca"), mock.patch("subprocess.run") as command:
            command.return_value = subprocess.CompletedProcess([], 0, stdout="[]", stderr="")
            report = report_for(data, orca.tasks_from_args(data, Namespace(orca_run="run_root")))
        command.assert_called_once()
        self.assertIs(report.as_dict().get("orca_requested_complete"), True)
        self.assertFalse(report.orca_complete)
        self.assertIn("run_storage", report.text())
        self.assertTrue({"nothing-behind", "no-recent-activity"}.isdisjoint(d.kind for d in report.drift))

    def test_a_failed_child_is_unknown_and_successful_runs_still_supply_evidence(self):
        data = owned_roadmap()
        no_stall_kinds = {"nothing-behind", "no-recent-activity"}

        def command(argv, **kwargs):
            run = argv[-2]
            if run == "run_storage":
                return subprocess.CompletedProcess(argv, 1, stdout="", stderr="error: run is unavailable")
            payload = [task("Unexpected worker")] if run == "run_root" else []
            return subprocess.CompletedProcess(argv, 0, stdout=json.dumps(payload), stderr="")

        with mock.patch("shutil.which", return_value="/fake/orca"), mock.patch("subprocess.run", side_effect=command):
            tasks = orca.tasks_from_args(data, Namespace())
        report = report_for(data, tasks)
        self.assertFalse(getattr(report, "orca_complete", True))
        self.assertEqual(report.errors, [])
        self.assertTrue(
            any("run_storage" in n and "Unknown" in n and "run is unavailable" in n for n in report.notes),
            report.notes,
        )
        kinds = {d.kind for d in report.drift}
        self.assertIn("unlinked-orca-task", kinds)
        self.assertTrue(kinds.isdisjoint(no_stall_kinds), kinds)
        self.assertTrue(report.status_changes)

    def test_malformed_success_responses_have_unknown_coverage(self):
        for payload in (
            {"ok": False, "error": "bad selection"},
            {"ok": True, "result": {}},
            {"tasks": None},
            [None],
            [{"title": "Missing id"}],
            "not a task list",
        ):
            with self.subTest(payload=payload):
                with mock.patch("shutil.which", return_value="/fake/orca"), mock.patch("subprocess.run") as run:
                    run.return_value = subprocess.CompletedProcess([], 0, stdout=json.dumps(payload), stderr="")
                    tasks = orca.tasks_from_args(sync_roadmap(), Namespace(orca_run="run_missing"))
                report = report_for(sync_roadmap(), tasks)
                self.assertFalse(getattr(report, "orca_complete", True))
                self.assertTrue(any("run_missing" in n and "Unknown" in n for n in report.notes), report.notes)
                self.assertNotIn("nothing-behind", {d.kind for d in report.drift})

    def test_missing_executable_is_unknown_with_selected_alias_and_no_fallback(self):
        with (
            mock.patch.dict("os.environ", {"ORCA_CLI_COMMAND": "missing-orca"}, clear=True),
            mock.patch("shutil.which", return_value=None),
            mock.patch("subprocess.run") as run,
        ):
            tasks = orca.tasks_from_args(sync_roadmap(), Namespace(orca_run="run_target"))
        run.assert_not_called()
        report = report_for(sync_roadmap(), tasks)
        self.assertFalse(getattr(report, "orca_complete", True))
        self.assertTrue(
            any(all(value in n for value in ("missing-orca", "run_target", "Unknown")) for n in report.notes),
            report.notes,
        )

    def test_managed_linux_dev_override_and_explicit_executable_selection(self):
        for env, expected in (
            ({}, "orca-ide"),
            ({"ORCA_TERMINAL_HANDLE": "term_here"}, "orca"),
            ({"ORCA_PANE_KEY": "pane_here"}, "orca"),
            ({"ORCA_DEV_REPO_ROOT": "/dev/checkout"}, "orca-dev"),
            (
                {"ORCA_CLI_COMMAND": "paired-orca; literal", "ORCA_DEV_REPO_ROOT": "/dev/checkout"},
                "paired-orca; literal",
            ),
        ):
            with (
                self.subTest(env=env),
                mock.patch.dict("os.environ", env, clear=True),
                mock.patch("sys.platform", "linux"),
                mock.patch("shutil.which", side_effect=lambda exe: exe),
                mock.patch("subprocess.run") as run,
            ):
                run.return_value = subprocess.CompletedProcess([], 0, stdout="[]", stderr="")
                self.assertEqual(orca.read_run("run_test"), [])
                self.assertEqual(run.call_args.args[0][0], expected)
                self.assertFalse(run.call_args.kwargs.get("shell", False))


class SyncWithNestedRuns(unittest.TestCase):
    def test_competing_top_level_containers_hold_coverage_and_keep_explicit_scopes(self):
        data = {**sync_roadmap(), "orca": {"run": "run_storage"}}
        scoped = task("Explicit flat task", runId="run_storage", id="task_scoped")
        named = task("Named run task", id="task_named")
        flat = [scoped, task("Unscoped competing task", id="task_unscoped")]
        for payload in (
            {"ok": True, "runs": {"run_other": [named]}, "result": {"tasks": flat}},
            {"runs": {"run_other": [named]}, "tasks": flat},
            {"tasks": flat, "result": {"runs": {"run_other": [named]}}},
            {"runs": {"run_other": [named]}, "result": flat},
        ):
            with self.subTest(payload=payload):
                report = report_for(data, collect_recorded(data, payload))
                self.assertFalse(report.orca_complete)
                self.assertFalse(report.orca_requested_complete)
                self.assertTrue({"nothing-behind", "no-recent-activity"}.isdisjoint(d.kind for d in report.drift))
                self.assertEqual(
                    {d.target for d in report.drift if d.kind == "unlinked-orca-task"},
                    {"run_other/task_named", "run_storage/task_scoped"},
                )

    def test_competing_per_run_containers_keep_scoped_siblings_and_hold_conflicting_tasks(self):
        data = {**sync_roadmap(), "orca": {"run": "run_storage"}}
        payload = {
            "runs": {
                "run_storage": {
                    "tasks": [task("Outer row", id="task_outer"), task("First version")],
                    "result": {
                        "runId": "run_storage",
                        "tasks": [task("Inner row", id="task_inner"), task("Second version")],
                    },
                },
                "run_other": [task("Sibling run", id="task_sibling")],
            }
        }
        report = report_for(data, collect_recorded(data, payload))
        self.assertFalse(report.orca_complete)
        self.assertFalse(report.orca_requested_complete)
        self.assertEqual(
            {d.target for d in report.drift if d.kind == "unlinked-orca-task"},
            {"run_storage/task_outer", "run_storage/task_inner", "run_other/task_sibling"},
        )

    def test_foreign_wrapper_scope_still_binds_competing_per_run_containers(self):
        data = {**sync_roadmap(), "orca": {"run": "run_storage"}}
        foreign = task("page-ranking: foreign worker", id="task_foreign")
        for extra in ({"runs": {"run_other": []}}, {"result": {"tasks": []}}):
            with self.subTest(extra=extra):
                payload = {
                    "runs": {
                        "run_storage": {
                            "ok": True,
                            "runId": "run_other",
                            "result": {"tasks": [foreign], **extra},
                        },
                        "run_sibling": [task("Independent evidence", id="task_sibling")],
                    }
                }
                report = report_for(data, collect_recorded(data, payload))
                self.assertFalse(report.orca_complete)
                self.assertFalse(report.orca_requested_complete)
                self.assertNotIn("run_storage/task_foreign", {d.target for d in report.drift})
                self.assertIn("run_sibling/task_sibling", {d.target for d in report.drift})
                self.assertIn("different run 'run_other'", report.text())

    def test_competing_per_run_task_list_and_nested_map_keep_both_scoped_positives(self):
        data = {**sync_roadmap(), "orca": {"run": "run_storage"}}
        payload = {
            "runs": {
                "run_storage": {
                    "tasks": [task("Outer evidence", id="task_outer", runId="run_storage")],
                    "result": {
                        "runs": {
                            "run_storage": [task("Inner evidence", id="task_inner", runId="run_storage")],
                            "run_other": [task("Foreign worker", id="task_foreign", runId="run_other")],
                        }
                    },
                }
            }
        }
        report = report_for(data, collect_recorded(data, payload))
        self.assertFalse(report.orca_complete)
        self.assertFalse(report.orca_requested_complete)
        self.assertTrue({"nothing-behind", "no-recent-activity"}.isdisjoint(d.kind for d in report.drift))
        self.assertEqual(
            {d.target for d in report.drift if d.kind == "unlinked-orca-task"},
            {"run_storage/task_outer", "run_storage/task_inner"},
        )

    def test_competing_task_containers_keep_each_envelopes_own_scope(self):
        data = {**sync_roadmap(), "orca": {"run": "run_storage"}}
        payload = {
            "runId": "run_other",
            "tasks": [task("Foreign evidence")],
            "result": {"runId": "run_storage", "tasks": [task("Configured evidence")]},
        }
        report = report_for(data, collect_recorded(data, payload))
        self.assertFalse(report.orca_complete)
        self.assertEqual(
            {d.target for d in report.drift if d.kind == "unlinked-orca-task"},
            {"run_other/task_same", "run_storage/task_same"},
        )

    def test_root_wrapper_scope_holds_conflicting_task_and_worker_evidence(self):
        data = {**sync_roadmap(), "orca": {"run": "run_storage"}}
        payload = {
            "runId": "run_other",
            "result": {
                "runId": "run_storage",
                "tasks": [task("page-ranking: repair", id="task_probe", dispatchId="d")],
                "result": {},
            },
            "workers": {"d": {**worker("task_probe", "d", "working"), "observed_at": OBSERVED}},
        }
        report = report_for(data, collect_recorded(data, payload))
        self.assertFalse(report.orca_complete)
        self.assertFalse(report.orca_requested_complete)
        self.assertNotIn("started-early", {d.kind for d in report.drift})
        self.assertEqual(report.orca_observation["workers"], [])
        self.assertIn("conflicting run scope", report.text())

    def test_ambiguous_wrapped_run_map_keeps_only_agreeing_rows_and_sibling_containers(self):
        data = {**sync_roadmap(), "orca": {"run": "run_storage"}}
        payload = {
            "run": "run_storage",
            "result": {
                "tasks": [task("Storage evidence", id="task_flat")],
                "runs": {
                    "run_storage": [task("Storage history", id="task_named")],
                    "run_other": [task("Other run", id="task_other")],
                },
            },
        }
        report = report_for(data, collect_recorded(data, payload))
        self.assertFalse(report.orca_complete)
        self.assertFalse(report.orca_requested_complete)
        self.assertEqual(
            {d.target for d in report.drift if d.kind == "unlinked-orca-task"},
            {"run_storage/task_flat", "run_storage/task_named"},
        )

    def test_failed_recording_envelopes_cannot_certify_a_run(self):
        data = {**sync_roadmap(), "orca": {"run": "run_root"}}
        for payload in (
            {"ok": False, "error": "recording interrupted", "runs": {"run_root": []}},
            {"result": {"ok": False, "error": "recording interrupted", "runs": {"run_root": []}}},
        ):
            with self.subTest(payload=payload):
                report = report_for(data, collect_recorded(data, payload))
                self.assertFalse(report.orca_complete)
                self.assertIn("recording interrupted", report.text())
                self.assertNotIn("nothing-behind", {d.kind for d in report.drift})

    def test_a_legacy_flat_recording_must_cover_its_only_expected_run(self):
        data = {**sync_roadmap(), "orca": {"run": "run_root"}}
        for payload in (
            [task("Unrelated work", run="run_other")],
            {"runId": "run_other", "tasks": []},
            [{"id": "task_bad", "run": " "}],
        ):
            with self.subTest(payload=payload):
                report = report_for(data, collect_recorded(data, payload))
                self.assertFalse(report.orca_complete)
                self.assertNotIn("nothing-behind", {d.kind for d in report.drift})
        unrelated = report_for(data, collect_recorded(data, [task("Unrelated work", run="run_other")]))
        self.assertIn("run_other/task_same", {d.target for d in unrelated.drift})
        self.assertIs(unrelated.as_dict().get("orca_requested_complete"), False)
        legacy = report_for(data, collect_recorded(data, []))
        self.assertTrue(legacy.orca_complete)
        self.assertIn("nothing-behind", {d.kind for d in legacy.drift})
        legacy = report_for(data, collect_recorded(data, [task("Legacy work")]))
        self.assertIn("task_same", {d.target for d in legacy.drift})

    def test_empty_recorded_run_map_names_the_unread_configured_runs(self):
        data = owned_roadmap()
        report = report_for(data, collect_recorded(data, {"runs": {}}))
        self.assertFalse(report.orca_complete)
        for run in ("run_root", "run_storage", "run_search", "run_release"):
            self.assertTrue(any(run in note and "missing run" in note for note in report.notes))

    def test_invalid_run_scope_and_duplicate_rows_hold_coverage_but_keep_good_evidence(self):
        data = {**sync_roadmap(), "orca": {"run": "run_root"}}
        report = report_for(
            data,
            collect_recorded(
                data,
                {
                    "runs": {
                        " ": [],
                        "run_root": [
                            task("Explicitly unrelated", runId="run_other"),
                            {"id": ""},
                            task("Recoverable sibling"),
                            task("Recoverable sibling"),
                        ],
                        "run_child": [task("Independent child")],
                    }
                },
            ),
        )
        self.assertFalse(report.orca_complete)
        self.assertIn("duplicate", report.text())
        self.assertIn("run_other", report.text())
        self.assertEqual(
            [d.target for d in report.drift if d.kind == "unlinked-orca-task"],
            ["run_root/task_same", "run_child/task_same"],
        )

    def test_duplicate_recorded_run_keys_cannot_certify_coverage(self):
        data = {**sync_roadmap(), "orca": {"run": "run_root"}}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "orca.json"
            path.write_text(
                '{"runs":{"run_root":[],"run_root":[],"run_child":[{"id":"task_child","title":"Child work"}]}}',
                encoding="utf-8",
            )
            report = report_for(data, orca.tasks_from_args(data, Namespace(orca_json=path)))
        self.assertFalse(report.orca_complete)
        self.assertIn("duplicate", report.text())
        self.assertIn("run_child/task_child", {d.target for d in report.drift})

    def test_conflicting_rows_for_one_task_do_not_supply_worker_activity(self):
        data = {**sync_roadmap(), "orca": {"run": "run_storage"}}
        recording = {
            "runs": {
                "run_storage": [
                    dispatched("task_conflict", "dispatch_old"),
                    dispatched("task_conflict", "dispatch_new"),
                    task("Unambiguous independent row"),
                ]
            },
            "workers": {
                "dispatch_old": {
                    **worker("task_conflict", "dispatch_old", "working"),
                    "observed_at": OBSERVED,
                }
            },
        }
        report = report_for(data, collect_recorded(data, recording))
        self.assertFalse(report.orca_complete)
        self.assertIn("run_storage/task_same", {d.target for d in report.drift})
        self.assertNotIn("task_conflict", {row["task"] for row in report.orca_observation["workers"]})

    def test_colliding_ids_do_not_combine_matches_or_started_status(self):
        tasks = collect_recorded(
            sync_roadmap(),
            {
                "runs": {
                    "run_one": [task("page-ranking: waiting", status="queued")],
                    "run_two": [task("Unexpected worker")],
                    "run_three": [task("Another unexpected worker")],
                }
            },
        )
        report = report_for(sync_roadmap(), tasks)
        self.assertTrue(getattr(report, "orca_complete", False))
        self.assertEqual(
            {d.target for d in report.drift if d.kind == "unlinked-orca-task"},
            {"run_two/task_same", "run_three/task_same"},
        )
        self.assertFalse([d for d in report.drift if d.kind == "started-early"])

    def test_only_explicit_coordination_avoids_unlinked_worker_drift(self):
        tasks = collect_recorded(
            sync_roadmap(),
            {
                "runs": {
                    "run_root": [
                        task("Orchestrate area work", kind="coordination"),
                        dict(task("page-ranking: wiring", kind="coordination"), id="task_linked"),
                        dict(task("Unlinked worker"), id="task_worker"),
                        dict(task("Old unlinked work", status="completed"), id="task_old"),
                    ],
                }
            },
        )
        report = report_for(sync_roadmap(), tasks)
        self.assertEqual({d.target for d in report.drift if d.kind == "unlinked-orca-task"}, {"run_root/task_worker"})
        self.assertEqual({d.target for d in report.drift if d.kind == "started-early"}, {"run_root/task_linked"})
        self.assertTrue(any("page-ranking" in d.message for d in report.drift if d.kind == "started-early"))

    def test_recorded_multi_run_requires_missing_configured_runs_to_be_visible(self):
        tasks = collect_recorded(
            owned_roadmap(),
            {
                "runs": {
                    "run_root": {"tasks": [task("Unsourced work")]},
                    "run_storage": {"error": "recording unavailable"},
                    "run_search": [],
                }
            },
        )
        report = report_for(owned_roadmap(), tasks)
        self.assertFalse(getattr(report, "orca_complete", True))
        for run, reason in (("run_storage", "recording unavailable"), ("run_release", "missing")):
            self.assertTrue(any(run in n and "Unknown" in n and reason in n for n in report.notes), report.notes)
        self.assertIn("run_root/task_same", {d.target for d in report.drift})

    def test_flat_recordings_and_no_orca_take_precedence_over_live_override(self):
        with mock.patch("subprocess.run") as run:
            for payload in (fixture("orca_tasks.json"), fixture("orca_tasks.json")["result"]["tasks"]):
                data = sync_roadmap()
                tasks = collect_recorded(data, payload, orca_run="run_ignored")
                self.assertEqual(
                    {d.target for d in report_for(data, tasks).drift if d.kind == "unlinked-orca-task"}, {"task_2"}
                )
            skipped = collect_recorded(data, None, no_orca=True, orca_run="run_ignored")
        self.assertEqual(skipped, "Orca not checked (--no-orca).")
        run.assert_not_called()

    def test_flat_recording_retains_evidence_but_cannot_confirm_coverage_of_multiple_runs(self):
        data = owned_roadmap()
        tasks = collect_recorded(data, fixture("orca_tasks.json"))
        report = report_for(data, tasks)
        self.assertFalse(getattr(report, "orca_complete", True))
        self.assertIn("task_2", {d.target for d in report.drift if d.kind == "unlinked-orca-task"})
        self.assertNotIn("nothing-behind", {d.kind for d in report.drift})

    def test_explicit_run_in_a_flat_recording_retains_configured_provenance(self):
        data = owned_roadmap()
        row = task("An unexpected worker", run="run_search", owner="original owner")
        tasks = collect_recorded(data, [row])
        self.assertEqual(tasks, [row])
        self.assertEqual(getattr(tasks[0], "source_run", None), "run_search")
        self.assertEqual(tasks[0].run_owners["search"]["parent"], "root")
        self.assertIn("run_search/task_same", {d.target for d in report_for(data, tasks).drift})

    def test_sync_and_drift_issue_report_unknown_without_applying_partial_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "roadmap.json"
            path.write_text(json.dumps(owned_roadmap()), encoding="utf-8")
            recording = Path(tmp) / "orca.json"
            recording.write_text(json.dumps({"runs": {"run_root": []}}), encoding="utf-8")
            common = [
                str(path),
                "--recorded",
                str(FIXTURES / "gitlab_sync.json"),
                "--orca-json",
                str(recording),
                "--now",
                "2026-11-17",
            ]
            for command, option in (("sync", "--update-drift-issue"), ("drift-issue", "--apply")):
                with self.subTest(command=command):
                    output = io.StringIO()
                    errors = io.StringIO()
                    with (
                        mock.patch("roadmaplib.driftissue.run") as apply,
                        redirect_stdout(output),
                        redirect_stderr(errors),
                    ):
                        code = cli.main([command, *common, option])
                    self.assertNotEqual(code, 0)
                    apply.assert_not_called()
                    self.assertIn("run_storage", output.getvalue())
                    self.assertIn("Unknown", output.getvalue())
                    self.assertIn("left as it is", output.getvalue() + errors.getvalue())


class WorkerObservation(unittest.TestCase):
    def test_program_zero_needs_activity_in_each_configured_run(self):
        payload = {
            "observed_at": OBSERVED,
            "runs": {
                "run_search": [task("Earlier search work", status="completed")],
                "run_storage": [dispatched("task_idle", "dispatch_idle")],
            },
            "workers": {
                "dispatch_idle": {**worker("task_idle", "dispatch_idle", "idle"), "observed_at": OBSERVED},
            },
        }
        for activity in ("idle", "working"):
            payload["workers"]["dispatch_idle"]["result"]["activity"] = activity
            for configured in (["run_search"], ["run_search", "run_storage"], ["run_storage"], []):
                with self.subTest(configured=configured, activity=activity):
                    data = sync_roadmap()
                    data.pop("orca", None)
                    data["orchestration"] = {"coordinators": {run: {"run": run} for run in configured}}
                    report = report_for(data, collect_recorded(data, payload))
                    self.assertTrue(report.orca_complete)
                    saved = json.loads(json.dumps(report.roadmap))
                    self.assertEqual(saved["orca_observation"]["configured_runs"], sorted(configured))
                    rows = saved["orca_observation"]["workers"]
                    self.assertEqual(
                        [(w["run"], w["activity"], w["observed_at"]) for w in rows],
                        [("run_storage", activity, OBSERVED)],
                    )
                    expected = "Worker activity is Unknown"
                    if activity == "working":
                        expected = "1 confirmed working"
                    elif configured == ["run_storage"]:
                        expected = "0 confirmed working"
                    for output in (report.text(), render.render_page(saved)):
                        self.assertIn(expected, output)
                        self.assertEqual("0 confirmed working" in output, expected == "0 confirmed working")
                        if "run_search" in configured:
                            self.assertIn("Activity is Unknown for run_search", output)

    def test_legacy_snapshot_without_capture_scope_keeps_idle_row_and_unknown_total(self):
        data = {**sync_roadmap(), "orca": {"run": "run_storage"}}
        data["orca_observation"] = {
            "source": "recorded",
            "observed_at": OBSERVED,
            "coverage_complete": True,
            "workers": [
                {
                    "run": "run_storage",
                    "task": "task_idle",
                    "dispatch": "dispatch_idle",
                    "observed_at": OBSERVED,
                    "activity": "idle",
                    "owners": {},
                }
            ],
        }
        page = render.render_page(data)
        self.assertIn("Idle", page)
        self.assertIn("Worker activity is Unknown", page)
        self.assertNotIn("0 confirmed working", page)
        for invalid in (None, "run_storage", [{}], [""]):
            with self.subTest(invalid=invalid):
                data["orca_observation"]["configured_runs"] = invalid
                with self.assertRaises(render.RenderError):
                    render.render_page(data)

    def test_recorded_outer_worker_identifiers_must_match_the_result(self):
        data = {**sync_roadmap(), "orca": {"run": "run_storage"}}
        identity = {"runId": "run_storage", "taskId": "task_work", "dispatchId": "dispatch_work"}
        entry = {**worker("task_work", "dispatch_work", "working"), **identity, "observed_at": OBSERVED}
        payload = {
            "runs": {"run_storage": [dispatched("task_work", "dispatch_work")]},
            "workers": {"dispatch_work": entry},
        }
        report = report_for(data, collect_recorded(data, payload))
        self.assertEqual(report.orca_observation["workers"][0]["activity"], "working")
        for key in identity:
            with self.subTest(key=key):
                payload["workers"]["dispatch_work"] = {**entry, key: "unrelated"}
                tasks = collect_recorded(data, payload)
                report = report_for(data, tasks)
                self.assertEqual([row["id"] for row in tasks], ["task_work"])
                self.assertTrue(report.orca_complete)
                row = report.orca_observation["workers"][0]
                self.assertEqual((row["activity"], row["observed_at"]), ("unknown", None))
                self.assertIn("1 Unknown", report.text())

    def test_live_outer_worker_identity_cannot_contradict_the_result(self):
        data = {**sync_roadmap(), "orca": {"run": "run_storage"}}
        task_rows = [dispatched("task_work", "dispatch_work")]
        response = {**worker("task_work", "dispatch_work", "working"), "taskId": "unrelated"}
        replies = [subprocess.CompletedProcess([], 0, json.dumps(value), "") for value in (task_rows, response)]
        with mock.patch("shutil.which", return_value="/fake/orca"), mock.patch("subprocess.run", side_effect=replies):
            report = report_for(data, orca.tasks_from_args(data, Namespace()))
        self.assertTrue(report.orca_complete)
        self.assertEqual(report.orca_observation["workers"][0]["activity"], "unknown")

    def test_known_dispatch_with_missing_lifecycle_has_unknown_activity(self):
        data = {**sync_roadmap(), "orca": {"run": "run_storage"}}
        partial = dispatched("task_partial", "dispatch_partial")
        del partial["status"]
        payload = {
            "runs": {"run_storage": [partial]},
            "workers": {
                "dispatch_partial": {
                    **worker("task_partial", "dispatch_partial", "working"),
                    "observed_at": OBSERVED,
                }
            },
        }
        report = report_for(data, collect_recorded(data, payload))
        self.assertTrue(report.orca_complete)
        workers = report.orca_observation["workers"]
        self.assertEqual([(row["dispatch"], row["activity"]) for row in workers], [("dispatch_partial", "unknown")])
        self.assertIn("Worker activity is Unknown", report.text())
        self.assertIn("1 Unknown", report.text())
        self.assertNotIn("0 confirmed working", report.text())
        self.assertNotIn("started-early", {d.kind for d in report.drift})

    def test_lifecycle_only_recording_keeps_activity_unknown_in_text_and_saved_render(self):
        data = {**sync_roadmap(), "orca": {"run": "run_storage"}}
        for recording in (
            [],
            [task("Earlier work", status="completed")],
            [task("Future work", status="queued")],
            {"observed_at": OBSERVED, "runs": {"run_storage": []}, "workers": {}},
        ):
            with self.subTest(recording=recording):
                report = report_for(data, collect_recorded(data, recording))
                self.assertTrue(report.orca_complete)
                self.assertTrue(report.orca_requested_complete)
                self.assertEqual(report.orca_observation["workers"], [])
                saved = json.loads(json.dumps(report.roadmap))
                self.assertEqual(
                    saved["orca_observation"]["observed_at"], OBSERVED if isinstance(recording, dict) else None
                )
                for output in (report.text(), render.render_page(saved)):
                    self.assertIn("Worker activity is Unknown", output)
                    self.assertNotIn("0 confirmed working", output)

    def test_zero_requires_timestamped_idle_observations_and_full_coverage(self):
        data = {**sync_roadmap(), "orca": {"run": "run_storage"}}
        payload = {
            "runs": {"run_storage": [dispatched("task_idle", "dispatch_idle")]},
            "workers": {
                "dispatch_idle": {**worker("task_idle", "dispatch_idle", "idle"), "observed_at": OBSERVED},
            },
        }
        for capture_time, missing_run, label in (
            (None, False, "Worker activity is Unknown"),
            (OBSERVED, True, "Worker activity is Unknown"),
            (OBSERVED, False, "0 confirmed working"),
        ):
            with self.subTest(capture_time=capture_time, missing_run=missing_run):
                data["orchestration"] = {"coordinators": {"extra": {"run": "run_missing"}}} if missing_run else {}
                report = report_for(data, collect_recorded(data, {**payload, "observed_at": capture_time}))
                self.assertEqual(report.orca_complete, not missing_run)
                self.assertEqual(report.orca_observation["workers"][0]["activity"], "idle")
                for output in (report.text(), render.render_page(report.roadmap)):
                    self.assertIn(label, output)
                    self.assertEqual("0 confirmed working" in output, label == "0 confirmed working")

    def test_recorded_activity_rejects_invalid_timezone_offsets(self):
        data = {**sync_roadmap(), "orca": {"run": "run_storage"}}
        payload = {"runs": {"run_storage": [dispatched("task_work", "dispatch_work")]}}
        for offset, expected_activity in (("+00:99", "unknown"), ("-03:60", "unknown"), ("+23:59", "working")):
            with self.subTest(offset=offset):
                timestamp = "2026-11-19T19:15:41" + offset
                payload["observed_at"] = timestamp
                payload["workers"] = {
                    "dispatch_work": {
                        **worker("task_work", "dispatch_work", "working"),
                        "observed_at": timestamp,
                    }
                }
                report = report_for(data, collect_recorded(data, payload))
                expected_time = timestamp if expected_activity == "working" else None
                snapshot = report.orca_observation
                row = snapshot["workers"][0]
                self.assertEqual((row["activity"], row["observed_at"]), (expected_activity, expected_time))
                self.assertEqual(snapshot["observed_at"], expected_time)

    def test_live_observation_respects_a_shared_deadline(self):
        data = {**sync_roadmap(), "orca": {"run": "run_storage"}}
        rows = [dispatched("task_first", "dispatch_first"), dispatched("task_second", "dispatch_second")]
        responses = [
            subprocess.CompletedProcess([], 0, json.dumps(rows), ""),
            subprocess.CompletedProcess([], 0, json.dumps(worker("task_first", "dispatch_first", "working")), ""),
        ]
        with (
            mock.patch("shutil.which", return_value="/fake/orca"),
            mock.patch("subprocess.run", side_effect=responses) as command,
            mock.patch("roadmaplib.orca.monotonic", side_effect=[0, 11, 16]),
        ):
            report = report_for(data, orca.tasks_from_args(data, Namespace()))
        self.assertEqual(command.call_count, 2)
        self.assertEqual(command.call_args.kwargs["timeout"], 4)
        self.assertEqual([row["activity"] for row in report.orca_observation["workers"]], ["working", "unknown"])
        self.assertTrue(report.orca_requested_complete)

    def test_live_reads_observe_each_relevant_dispatch_once_and_keep_unknowns(self):
        data = owned_roadmap()
        data["orchestration"]["coordinators"]["partner"] = {"run": "run_storage", "parent": "search"}
        rows = [
            dispatched("task_work", "dispatch_work"),
            dispatched("task_wait", "dispatch_wait"),
            dispatched("task_idle", "dispatch_idle"),
            dispatched("task_stopped", "dispatch_stopped"),
            dispatched("task_unavailable", "dispatch_unavailable"),
            dispatched("task_duplicate_dispatch", "dispatch_work"),
            dispatched("task_unknown", "dispatch_unknown"),
            dispatched("task_no_dispatch", None),
            {"id": "task_queued", "status": "queued", "dispatchId": "dispatch_queued"},
            {"id": "task_done", "status": "completed", "dispatchId": "dispatch_done"},
        ]
        answers = {
            "dispatch_work": worker("task_work", "dispatch_work", "working"),
            "dispatch_wait": worker("task_wait", "dispatch_wait", "waiting"),
            "dispatch_idle": worker("task_idle", "dispatch_idle", "idle"),
            "dispatch_stopped": worker("task_stopped", "dispatch_stopped", "working", state="failed"),
            "dispatch_unknown": worker("task_unknown", "dispatch_unknown", None),
        }
        reads = []

        def command(argv, **kwargs):
            if argv[2] == "task-list":
                payload = {"ok": True, "result": {"tasks": rows if argv[-2] == "run_storage" else []}}
            else:
                self.assertEqual(argv[2:4], ["worker-show", "--dispatch"])
                self.assertGreater(kwargs["timeout"], 0)
                self.assertLessEqual(kwargs["timeout"], 30)
                dispatch = argv[-2]
                reads.append(dispatch)
                if dispatch == "dispatch_unavailable":
                    raise subprocess.TimeoutExpired(argv, kwargs["timeout"])
                payload = answers[dispatch]
            return subprocess.CompletedProcess(argv, 0, stdout=json.dumps(payload), stderr="")

        with (
            mock.patch("shutil.which", return_value="/fake/orca"),
            mock.patch("subprocess.run", side_effect=command),
            mock.patch("roadmaplib.orca.datetime", wraps=datetime, create=True) as clock,
        ):
            clock.now.return_value = datetime(2026, 11, 19, 19, 15, 41, 234000, tzinfo=timezone.utc)
            report = report_for(data, orca.tasks_from_args(data, Namespace()))
        self.assertCountEqual(reads, [*answers, "dispatch_unavailable"])
        self.assertTrue(report.orca_complete)
        observation = report.as_dict().get("orca_observation", {})
        by_task = {row["task"]: row for row in observation.get("workers", [])}
        self.assertEqual(
            {key: row["activity"] for key, row in by_task.items()},
            {
                "task_work": "working",
                "task_wait": "waiting",
                "task_idle": "idle",
                "task_stopped": "stopped",
                "task_unavailable": "unknown",
                "task_duplicate_dispatch": "unknown",
                "task_unknown": "unknown",
                "task_no_dispatch": "unknown",
            },
        )
        self.assertEqual(by_task["task_work"]["observed_at"], "2026-11-19T19:15:41.234000+00:00")
        self.assertEqual(by_task["task_work"]["run"], "run_storage")
        self.assertEqual(by_task["task_work"]["dispatch"], "dispatch_work")
        self.assertEqual(by_task["task_work"]["owners"], {"partner": "search", "storage": "root"})
        self.assertIn("1 confirmed working", report.text())
        self.assertIn("4 Unknown", report.text())
        self.assertIn("no-recent-activity", {d.kind for d in report.drift})

    def test_recorded_activity_keeps_capture_time_and_undated_work_is_unknown(self):
        data = owned_roadmap()
        payload = {"runs": {run: [] for run in ("run_root", "run_storage", "run_search", "run_release")}}
        payload["runs"]["run_storage"] = [
            dispatched("task_work", "dispatch_work"),
            dispatched("task_undated", "dispatch_undated"),
            dispatched("task_queued_worker", "dispatch_queued_worker"),
        ]
        payload["workers"] = {
            "dispatch_work": {**worker("task_work", "dispatch_work", "working"), "observed_at": OBSERVED},
            "dispatch_undated": worker("task_undated", "dispatch_undated", "working"),
            "dispatch_queued_worker": {
                **worker("task_queued_worker", "dispatch_queued_worker", "queued"),
                "observed_at": OBSERVED,
            },
        }
        with mock.patch("subprocess.run") as run:
            report = report_for(data, collect_recorded(data, payload, orca_run="run_ignored"))
        run.assert_not_called()
        snapshot = report.as_dict().get("orca_observation", {})
        self.assertEqual(snapshot, report.roadmap.get("orca_observation"))
        by_task = {row["task"]: row for row in snapshot.get("workers", [])}
        self.assertEqual(
            {key: (row["activity"], row["observed_at"]) for key, row in by_task.items()},
            {
                "task_work": ("working", OBSERVED),
                "task_undated": ("unknown", None),
                "task_queued_worker": ("queued", OBSERVED),
            },
        )
        self.assertIn(OBSERVED, render.render_page(report.roadmap))
        self.assertIn("1 confirmed working", report.text())
        self.assertIn("1 confirmed working", render.render_page(report.roadmap))

    def test_only_skips_collection_and_preserves_global_observation_on_save(self):
        data = owned_roadmap()
        evidence = {
            "runs": {"run_storage": [dispatched("task_work", "dispatch_work")]},
            "workers": {
                "dispatch_work": {**worker("task_work", "dispatch_work", "working"), "observed_at": OBSERVED},
            },
        }
        data["orca_observation"] = collect_recorded(data, evidence).observation
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "roadmap.json"
            recording = Path(tmp) / "orca.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            recording.write_text("[]", encoding="utf-8")
            initial = path.read_bytes()
            args = [
                "sync",
                str(path),
                "--only",
                "ranking-model",
                "--recorded",
                str(FIXTURES / "gitlab_sync.json"),
                "--orca-json",
                str(recording),
                "--now",
                "2026-11-17",
                "--json",
            ]
            for extra in ([], ["--write"]):
                with (
                    self.subTest(extra=extra),
                    redirect_stdout(io.StringIO()) as output,
                    mock.patch("roadmaplib.orca.tasks_from_args", wraps=orca.tasks_from_args) as collect,
                    mock.patch("roadmaplib.model.save") as save,
                ):
                    self.assertEqual(cli.main([*args, *extra]), 0)
                    report, _ = json.JSONDecoder().raw_decode(output.getvalue())
                    self.assertEqual(report["status_changes"][0]["issue"], "ranking-model")
                    self.assertIsNone(report["orca_observation"])
                    self.assertIsNone(report["orca_complete"])
                    self.assertIsNone(report["orca_requested_complete"])
                    collect.assert_not_called()
                    if extra:
                        save.assert_called_once()
                        self.assertEqual(save.call_args.args[1]["orca_observation"], data["orca_observation"])
                    else:
                        save.assert_not_called()
                    self.assertEqual(path.read_bytes(), initial)

    def test_library_issue_scope_ignores_supplied_orca_collection(self):
        data = {**sync_roadmap(), "orca": {"run": "run_storage"}}
        data["orca_observation"] = collect_recorded(
            data, {"observed_at": OBSERVED, "runs": {"run_storage": []}}
        ).observation
        tasks = collect_recorded(data, [])
        fg = forge.GitLab(
            NoWrites(fixture("gitlab_sync.json")), host="gitlab.example.com", project="acme/search", group="acme"
        )
        report = sync.sync(data, fg, orca_tasks=tasks, only={"ranking-model"}, now="2026-11-17")
        self.assertEqual(report.roadmap["orca_observation"], data["orca_observation"])
        self.assertIsNone(report.orca_observation)
        self.assertIsNone(report.orca_complete)
        self.assertFalse(report.observation_changed)

    def test_sync_write_persists_snapshot_without_other_changes_and_no_orca_preserves_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "roadmap.json"
            recording = Path(tmp) / "orca.json"
            path.write_text(json.dumps(quiet()), encoding="utf-8")
            payload = {"runs": {"run_storage": [dispatched("task_work", "dispatch_work")]}}
            recording.write_text(json.dumps(payload), encoding="utf-8")
            common = [str(path), "--recorded", str(FIXTURES / "gitlab_sync.json"), "--now", "2026-11-17", "--write"]
            with (
                redirect_stdout(io.StringIO()),
                mock.patch("roadmaplib.forge.from_args", return_value=github(fresh_forge())),
                mock.patch("roadmaplib.model.save", wraps=cli.model.save) as save,
            ):
                self.assertEqual(cli.main(["sync", *common, "--orca-json", str(recording)]), 0)
                snapshot = json.loads(path.read_text()).get("orca_observation")
                self.assertEqual(cli.main(["sync", *common, "--orca-json", str(recording)]), 0)
                self.assertEqual(cli.main(["sync", *common, "--no-orca"]), 0)
            self.assertIsNotNone(snapshot)
            self.assertEqual(json.loads(path.read_text()).get("orca_observation"), snapshot)
            save.assert_called_once()


if __name__ == "__main__":
    unittest.main()
