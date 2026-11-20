"""orchestration.levels: the model, effort and parallel cap the lead chose at kickoff."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from helpers import CLI, FIXTURES, SCHEMA, example, fixture
from roadmaplib import forge, model, publish, render, sync, validate
from test_publish import NoWrites
from test_sync import sync_roadmap

WHERE = "orchestration.levels"


def recorded_levels() -> dict:
    return deepcopy(example()["orchestration"]["levels"])


def with_levels(value) -> dict:
    data = example()
    data["orchestration"]["levels"] = value
    return data


def level_warnings(data: dict) -> set[str]:
    """Where each levels problem is. Levels problems are warnings, never errors."""
    findings = validate.check(data)
    assert not validate.errors(findings), [str(f) for f in validate.errors(findings)]
    return {f.where for f in findings if f.code == "bad-levels" and f.level == "warning"}


def broken_levels(data: dict) -> dict:
    """A partial, mistyped kickoff answer: no epic or reviewer, a text cap, a blank effort."""
    data.setdefault("orchestration", {})["levels"] = {
        "program": {"model": "most-capable", "effort": ""},
        "worker": {"implementer": {"model": "mid-tier"}},
        "parallel_epics": "2",
    }
    return data


class LevelsSchema(unittest.TestCase):
    def test_schema_documents_the_fields_validate_checks(self):
        schema = json.loads(SCHEMA.read_text())
        ref = schema["properties"]["orchestration"]["properties"]["levels"]["$ref"]
        levels = schema["$defs"][ref.rsplit("/", 1)[-1]]
        self.assertEqual(set(levels["properties"]), set(model.LEVEL_FIELDS))
        self.assertEqual(set(levels["required"]), set(model.REQUIRED_LEVEL_FIELDS))
        self.assertIs(levels["additionalProperties"], False)
        cap = levels["properties"]["parallel_epics"]
        self.assertEqual((cap["type"], cap["minimum"]), ("integer", 1))
        worker = levels["properties"]["worker"]
        self.assertEqual(set(worker["required"]), set(model.REQUIRED_WORKER_ROLES))
        self.assertEqual(worker["propertyNames"]["pattern"], model.ROLE_KEY.pattern)
        tier = schema["$defs"]["tier"]
        self.assertEqual(set(tier["properties"]), set(model.TIER_FIELDS))
        self.assertEqual(tier["required"], ["model"])
        self.assertIs(tier["additionalProperties"], False)

    def test_example_records_every_level_and_the_default_cap(self):
        levels = recorded_levels()
        for level in model.LEVELS:
            self.assertIn("model", levels[level] if level != "worker" else levels[level]["implementer"])
        self.assertEqual(set(levels["worker"]), set(model.WORKER_ROLES))
        self.assertEqual(levels["parallel_epics"], model.DEFAULT_PARALLEL_EPICS)
        self.assertEqual(model.DEFAULT_PARALLEL_EPICS, 2)
        self.assertFalse(validate.errors(validate.check(example())))

    def test_roadmap_without_levels_stays_valid(self):
        data = example()
        del data["orchestration"]
        self.assertFalse(validate.errors(validate.check(data)))


class LevelsAccepted(unittest.TestCase):
    def test_named_exceptions_and_optional_fields_are_accepted(self):
        levels = recorded_levels()
        levels["worker"]["security_reviewer"] = {"model": "most-capable", "note": "auth and secrets changes"}
        levels["epic"] = {"model": "mid-tier", "agent": "codex"}
        levels["parallel_epics"] = 3
        levels["answered_by"] = "Program lead"
        levels["answered_on"] = "2026-11-20"
        self.assertEqual(level_warnings(with_levels(levels)), set())


class LevelsWarned(unittest.TestCase):
    def check_rejects(self, change, where):
        levels = recorded_levels()
        change(levels)
        self.assertIn(where, level_warnings(with_levels(levels)))

    def test_levels_must_be_an_object(self):
        self.assertIn(WHERE, level_warnings(with_levels(["program", "epic"])))

    def test_every_level_and_the_cap_are_required(self):
        for key in model.REQUIRED_LEVEL_FIELDS:
            with self.subTest(missing=key):
                self.check_rejects(lambda lv, key=key: lv.pop(key), WHERE)

    def test_a_misspelled_level_is_reported(self):
        self.check_rejects(lambda lv: lv.update(progam={"model": "x"}), f"{WHERE}.progam")

    def test_a_tier_needs_an_object_with_a_model(self):
        self.check_rejects(lambda lv: lv.update(program="most-capable"), f"{WHERE}.program")
        self.check_rejects(lambda lv: lv["program"].pop("model"), f"{WHERE}.program")
        self.check_rejects(lambda lv: lv["program"].update(model="  "), f"{WHERE}.program.model")

    def test_tier_text_fields_must_be_nonblank_text(self):
        for field in ("effort", "agent", "note"):
            with self.subTest(field=field):
                self.check_rejects(lambda lv, field=field: lv["epic"].update({field: 3}), f"{WHERE}.epic.{field}")

    def test_a_misspelled_tier_field_is_reported(self):
        self.check_rejects(lambda lv: lv["epic"].update(efort="high"), f"{WHERE}.epic.efort")

    def test_worker_roles_need_an_implementer_and_a_reviewer(self):
        for role in model.REQUIRED_WORKER_ROLES:
            with self.subTest(missing=role):
                self.check_rejects(lambda lv, role=role: lv["worker"].pop(role), f"{WHERE}.worker")

    def test_worker_must_map_role_names_to_tiers(self):
        self.check_rejects(lambda lv: lv.update(worker=["implementer"]), f"{WHERE}.worker")
        self.check_rejects(lambda lv: lv["worker"].update({"Final Reviewer": {"model": "x"}}), f"{WHERE}.worker.Final Reviewer")
        self.check_rejects(lambda lv: lv["worker"].update(mechanical={"effort": "low"}), f"{WHERE}.worker.mechanical")
        self.check_rejects(lambda lv: lv["worker"].update({"tester\n": {"model": "x"}}), f"{WHERE}.worker.tester\n")

    def test_parallel_epics_is_a_positive_whole_number(self):
        for bad in (0, -1, 1.5, "2", True, None):
            with self.subTest(parallel_epics=bad):
                self.check_rejects(lambda lv, bad=bad: lv.update(parallel_epics=bad), f"{WHERE}.parallel_epics")

    def test_who_answered_and_when_are_nonblank_text(self):
        for field in ("answered_by", "answered_on"):
            with self.subTest(field=field):
                self.check_rejects(lambda lv, field=field: lv.update({field: ""}), f"{WHERE}.{field}")



class BadLevelsKeepTheRoadmapWorking(unittest.TestCase):
    """The levels record is advisory: a slip in it must not stop the page, sync, publish or the hooks."""

    def test_validate_warns_and_exits_0(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "roadmap.json"
            path.write_text(json.dumps(broken_levels(example())))
            out = subprocess.run([sys.executable, str(CLI), "validate", str(path)], capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("warning: orchestration.levels", out.stdout)
        self.assertIn("[bad-levels]", out.stdout)

    def test_render_still_draws_the_page(self):
        self.assertIn("<html", render.render_page(broken_levels(example())))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "roadmap.json"
            path.write_text(json.dumps(broken_levels(example())))
            out = subprocess.run([sys.executable, str(CLI), "render", str(path), "-o", str(Path(tmp) / "p.html")],
                                 capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)

    def test_sync_only_as_the_hooks_run_it_still_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "roadmap.json"
            path.write_text(json.dumps(broken_levels(sync_roadmap())))
            out = subprocess.run([sys.executable, str(CLI), "sync", str(path), "--json", "--no-orca", "--only",
                                  "ranking-model", "--recorded", str(FIXTURES / "gitlab_sync.json"),
                                  "--now", "2026-11-17"], capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertEqual(json.loads(out.stdout)["errors"], [])

    def test_full_sync_still_runs(self):
        fg = forge.GitLab(NoWrites(fixture("gitlab_sync.json")), host="gitlab.example.com",
                          project="acme/search", group="acme")
        report = sync.sync(broken_levels(sync_roadmap()), fg, orca_tasks=None, now="2026-11-17")
        self.assertEqual(report.errors, [])

    def test_publish_dry_run_still_runs(self):
        fg = forge.GitHub(NoWrites(fixture("github_publish.json")), host="github.com",
                          project="example-org/search-service")
        report = publish.publish(broken_levels(example()), fg, apply=False)
        self.assertTrue(report.actions)


if __name__ == "__main__":
    unittest.main()
