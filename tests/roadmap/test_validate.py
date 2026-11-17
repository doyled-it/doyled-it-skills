"""validate: schema, cycles, dangling dependencies, and glossary checks."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import CLI, EXAMPLE, SCHEMA, example, issue
from roadmaplib import model, validate


def codes(findings, level=None):
    return {f.code for f in findings if level is None or f.level == level}


class ValidateExample(unittest.TestCase):
    def test_example_roadmap_is_clean(self):
        findings = validate.check(example())
        self.assertEqual([f for f in findings if f.level == "error"], [])

    def test_schema_file_matches_code_constants(self):
        schema = json.loads(SCHEMA.read_text())
        issue_props = schema["$defs"]["issue"]["properties"]
        self.assertEqual(sorted(issue_props["status"]["enum"]), sorted(model.STATUSES))
        self.assertIn("depends_on", issue_props)
        for key in ("title", "goal", "rule", "gates", "epics", "issues"):
            self.assertIn(key, schema["required"])


class StructuralErrors(unittest.TestCase):
    def test_dangling_dependency(self):
        data = example()
        issue(data, "page-build")["depends_on"].append("no-such-issue")
        self.assertIn("dangling-dependency", codes(validate.check(data), "error"))

    def test_cycle_is_reported_with_its_path(self):
        data = example()
        issue(data, "click-signals")["depends_on"] = ["ranking-check"]
        found = [f for f in validate.check(data) if f.code == "cycle"]
        self.assertTrue(found)
        self.assertIn("click-signals", found[0].message)
        self.assertIn("ranking-model", found[0].message)

    def test_self_dependency(self):
        data = example()
        issue(data, "page-build")["depends_on"] = ["page-build"]
        self.assertIn("cycle", codes(validate.check(data), "error"))

    def test_unknown_epic_status_and_gate(self):
        data = example()
        issue(data, "page-build")["epic"] = "nowhere"
        issue(data, "page-design")["status"] = "doing"
        issue(data, "weekly-release")["gates"].append("Z")
        got = codes(validate.check(data), "error")
        self.assertTrue({"unknown-epic", "bad-status", "unknown-gate"} <= got)

    def test_duplicate_ids_and_missing_fields(self):
        data = example()
        data["issues"].append(dict(issue(data, "page-build")))
        del data["goal"]
        del issue(data, "page-design")["title"]
        got = codes(validate.check(data), "error")
        self.assertTrue({"duplicate-id", "missing-field"} <= got)

    def test_issue_longer_than_two_weeks_must_become_an_epic(self):
        data = example()
        issue(data, "page-build")["estimate_days"] = 15
        self.assertIn("too-big", codes(validate.check(data), "error"))

    def test_unknown_parent_epic_and_iteration(self):
        data = example()
        data["epics"][1]["parent"] = "missing-epic"
        issue(data, "page-build")["iteration"] = "Iteration 9"
        got = codes(validate.check(data), "error")
        self.assertTrue({"unknown-parent", "unknown-iteration"} <= got)


class GlossaryChecks(unittest.TestCase):
    def test_milestone_is_never_allowed(self):
        data = example()
        data["rule"] = "Updates come at milestones."
        found = [f for f in validate.check(data) if f.code == "glossary-milestone"]
        self.assertEqual(found[0].level, "error")
        self.assertIn("rule", found[0].where)

    def test_codes_instead_of_names_are_rejected(self):
        data = example()
        issue(data, "page-build")["title"] = "T1.1 build the page"
        data["epics"][0]["name"] = "E2 Better ranking"
        found = [f for f in validate.check(data) if f.code == "glossary-code"]
        self.assertEqual(len(found), 2)

    def test_ids_must_be_short_readable_names(self):
        data = example()
        issue(data, "page-build")["id"] = "A1"
        issue(data, "page-ranking")["depends_on"] = ["A1", "ranking-check"]
        self.assertIn("unreadable-id", codes(validate.check(data), "error"))

    def test_synonyms_are_warnings(self):
        data = example()
        issue(data, "page-build")["detail"] = "Finish this sprint, see the ticket"
        got = codes(validate.check(data), "warning")
        self.assertIn("glossary-term", got)


class Warnings(unittest.TestCase):
    def test_done_with_unpassed_gates(self):
        data = example()
        issue(data, "page-design")["status"] = "done"
        self.assertIn("done-gates-open", codes(validate.check(data), "warning"))

    def test_started_before_dependencies_done(self):
        data = example()
        issue(data, "page-build")["status"] = "in_progress"
        self.assertIn("started-early", codes(validate.check(data), "warning"))


class LegacyFields(unittest.TestCase):
    def test_issue_and_issue_url_become_ref_and_url(self):
        data = example()
        it = issue(data, "page-build")
        it["issue"] = "group/app#5"
        it["issue_url"] = "https://gitlab.example.com/group/app/-/issues/5"
        loaded = model.normalize(data)
        got = issue(loaded, "page-build")
        self.assertEqual(got["ref"], "group/app#5")
        self.assertEqual(got["url"], "https://gitlab.example.com/group/app/-/issues/5")

    def test_gates_normalize_to_objects(self):
        loaded = model.normalize(example())
        gates = issue(loaded, "ranking-model")["gates"]
        self.assertEqual(gates[0]["gate"], "D")
        self.assertTrue(gates[0]["passed"])
        self.assertEqual(gates[1], {"gate": "R", "passed": False})


class ValidateCommand(unittest.TestCase):
    def run_cli(self, path):
        return subprocess.run([sys.executable, str(CLI), "validate", str(path)],
                              capture_output=True, text=True)

    def test_clean_roadmap_exits_zero(self):
        out = self.run_cli(EXAMPLE)
        self.assertEqual(out.returncode, 0, out.stderr + out.stdout)
        self.assertIn("0 errors", out.stdout)

    def test_errors_exit_nonzero_and_name_the_problem(self):
        data = example()
        issue(data, "page-build")["depends_on"] = ["ghost"]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "roadmap.json"
            path.write_text(json.dumps(data))
            out = self.run_cli(path)
        self.assertEqual(out.returncode, 1)
        self.assertIn("ghost", out.stdout)

    def test_invalid_json_is_a_clear_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "roadmap.json"
            path.write_text("{not json")
            out = self.run_cli(path)
        self.assertEqual(out.returncode, 1)
        self.assertIn("not valid JSON", out.stdout + out.stderr)


if __name__ == "__main__":
    unittest.main()
