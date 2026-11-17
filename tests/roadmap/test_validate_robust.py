"""validate reports wrong types instead of crashing, handles deep chains, and knows technical words."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from helpers import FIXTURES, example, issue
from roadmaplib import cli, render, validate


def codes(data):
    return {f.code for f in validate.errors(validate.check(data))}


class WrongTypesAreFindings(unittest.TestCase):
    def check(self, mutate, code="bad-type"):
        data = example()
        mutate(data)
        self.assertIn(code, codes(data))
        with self.assertRaises(render.RenderError):
            render.render_page(data)

    def test_entries_that_are_not_objects(self):
        self.check(lambda d: d["issues"].append("oops"))
        self.check(lambda d: d["epics"].append(5))

    def test_fields_with_the_wrong_type(self):
        self.check(lambda d: issue(d, "page-build").__setitem__("id", ["page", "build"]))
        self.check(lambda d: issue(d, "page-build").__setitem__("title", 12))
        self.check(lambda d: d["epics"][1].__setitem__("id", 7))
        self.check(lambda d: d["issues"].append(dict(issue(d, "page-build"), id=42)))
        self.check(lambda d: issue(d, "page-build").__setitem__("detail", ["a"]))
        self.check(lambda d: issue(d, "page-build").__setitem__("merge_requests", [5]))

    def test_iterations_and_timeline_must_be_lists_of_objects(self):
        for key in ("iterations", "timeline"):
            for value in (5, "soon", {"name": "x"}, [5], ["text"]):
                with self.subTest(key=key, value=value):
                    data = example()
                    data[key] = value
                    found = [f for f in validate.errors(validate.check(data)) if f.code == "bad-type"]
                    self.assertTrue(found and found[0].where.startswith(key), found)
                    with self.assertRaises(render.RenderError):
                        render.render_page(data)

    def test_an_approval_record_must_name_who_approved(self):
        for who in (True, 1, "", "  ", ["the lead"]):
            with self.subTest(who=who):
                data = example()
                issue(data, "page-design")["gates"] = [{"gate": "U", "passed": True, "approved_by": who,
                                                        "approved_on": "2026-11-17"}, "D"]
                self.assertIn("unrecorded-approval", codes(data))
        data = example()
        issue(data, "page-design")["gates"] = [{"gate": "U", "passed": True, "approved_by": "the program lead",
                                                "approved_on": 20261117}, "D"]
        self.assertIn("bad-type", codes(data))

    def test_depends_on_must_be_a_list_of_ids(self):
        data = example()
        issue(data, "page-build")["depends_on"] = "page-design"
        found = validate.check(data)
        self.assertIn("bad-type", {f.code for f in found})
        self.assertFalse([f for f in found if f.code == "dangling-dependency"])   # not one error per letter

    def test_estimate_must_be_a_number(self):
        data = example()
        issue(data, "page-build")["estimate_days"] = "30"
        self.assertIn("bad-type", codes(data))

    def test_gate_letters_and_entries(self):
        for gates in ({"Design review": "x"}, {"d": "x"}, {"DD": "x"}):
            data = example()
            data["gates"].update(gates)
            with self.subTest(gates=gates):
                self.assertIn("bad-gate", codes(data))
        data = example()
        issue(data, "page-build")["gates"] = [3, {"passed": True}]
        self.assertIn("bad-type", codes(data))

    def test_cli_prints_findings_not_a_traceback(self):
        data = example()
        data["issues"].append("oops")
        issue(data, "page-build")["depends_on"] = "page-design"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "roadmap.json"
            path.write_text(json.dumps(data))
            out = io.StringIO()
            with redirect_stdout(out):
                code = cli.main(["validate", str(path)])
        self.assertEqual(code, 1)
        self.assertIn("bad-type", out.getvalue())


class OddTypesAreNamed(unittest.TestCase):
    """Each wrongly typed field is a finding that says what it must be, never a crash."""

    def found(self, key, value):
        data = example()
        data[key] = value
        return [f for f in validate.errors(validate.check(data)) if f.code == "bad-type"]

    def test_iterations_need_text_names(self):
        for value in ([{"name": ["x"]}], [{"name": 5}], [{"name": "Week 1", "start": 3}]):
            with self.subTest(value=value):
                found = self.found("iterations", value)
                self.assertTrue(found and found[0].where.startswith("iterations[0]"), found)
                self.assertIn("must be text", found[0].message)

    def test_allowed_terms_must_be_a_list_of_text(self):
        for value in (5, True, "GP3", [5], [["GP3"]]):
            with self.subTest(value=value):
                found = self.found("allowed_terms", value)
                self.assertTrue(found and found[0].where == "allowed_terms", found)
                self.assertIn("list of words", found[0].message)

    def test_orca_must_be_an_object_with_a_text_run(self):
        for value, where in ((5, "orca"), ("run-1", "orca"), ([{}], "orca"), ({"run": 5}, "orca.run"),
                             ({"run": ["x"]}, "orca.run")):
            with self.subTest(value=value):
                found = self.found("orca", value)
                self.assertTrue(found and found[0].where == where, found)

    def test_lead_gates_must_be_letters(self):
        for value in ([{}], [["U"]], [5], "U"):
            with self.subTest(value=value):
                data = example()
                data["lead_gates"] = value
                self.assertIn("bad-lead-gates", codes(data))

    def test_forge_fields_must_be_text(self):
        for key, value in (("project", 5), ("project", ["a/b"]), ("group", 5), ("host", ["x"]), ("projects", "a/b"),
                           ("projects", [5]), ("status_labels", ["x"]), ("status_labels", {"blocked": 5})):
            with self.subTest(key=key, value=value):
                data = example()
                data["forge"][key] = value
                found = [f for f in validate.errors(validate.check(data)) if f.code == "bad-type"]
                self.assertTrue(found and found[0].where == f"forge.{key}", found)
        data = example()
        data["forge"] = 5
        self.assertTrue(validate.errors(validate.check(data)))


class OddTypesNeverCrashACommand(unittest.TestCase):
    """validate, sync and drift-issue print findings or an error for any odd type: never a traceback."""

    ODD = (5, "x", True, [5], [["x"]], {"a": 1}, [{"name": ["x"]}], {"run": 5}, None)
    KEYS = ("iterations", "allowed_terms", "orca", "lead_gates", "timeline", "gates", "forge", "forge.host",
            "forge.project", "forge.group", "forge.projects", "forge.status_labels", "forge.gate_rules")

    def test_every_command_survives(self):
        from test_sync import sync_roadmap

        recorded = str(FIXTURES / "gitlab_sync.json")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "roadmap.json"
            for key in self.KEYS:
                for value in self.ODD:
                    data = sync_roadmap()
                    if "." in key:
                        data["forge"][key.split(".")[1]] = value
                    else:
                        data[key] = value
                    path.write_text(json.dumps(data))
                    orca = [] if key == "orca" else ["--orca-json", str(FIXTURES / "orca_tasks.json")]
                    for argv in (["validate", str(path)],
                                 ["sync", str(path), "--recorded", recorded, "--now", "2026-11-17", *orca],
                                 ["drift-issue", str(path), "--recorded", recorded, "--now", "2026-11-17", *orca]):
                        with self.subTest(key=key, value=value, command=argv[0]), redirect_stdout(io.StringIO()):
                            self.assertIn(cli.main(argv), (0, 1, 2))


class DeepChains(unittest.TestCase):
    def chain(self, n):
        data = example()
        data["issues"] = []
        for k in range(n):
            data["issues"].append({"id": f"step-{k}", "title": f"Step number {k} of the chain", "epic": "ranking",
                                   "status": "to_do", "depends_on": [f"step-{k + 1}"] if k + 1 < n else []})
        return data

    def test_a_long_chain_listed_dependents_first(self):
        data = self.chain(1500)
        self.assertFalse(codes(data))
        self.assertIn("step-1499", render.render_page(data))

    def test_a_long_loop_is_still_found(self):
        data = self.chain(1500)
        data["issues"][-1]["depends_on"] = ["step-0"]
        self.assertIn("cycle", codes(data))


class TechnicalWords(unittest.TestCase):
    def test_common_technical_words_are_not_codes(self):
        data = example()
        issue(data, "page-build")["title"] = "Store blobs in S3 and serve over HTTP2 with UTF8 and IPv6"
        self.assertNotIn("glossary-code", codes(data))

    def test_work_codes_are_still_codes(self):
        for title in ("Finish T1.1", "Ship E2", "Do ABCD12", "Build TE4 next"):
            data = example()
            issue(data, "page-build")["title"] = title
            with self.subTest(title=title):
                self.assertIn("glossary-code", codes(data))

    def test_a_roadmap_can_allow_its_own_terms(self):
        data = example()
        issue(data, "page-build")["title"] = "Move logs to the GP3 volumes"
        self.assertIn("glossary-code", codes(data))
        data["allowed_terms"] = ["GP3"]
        self.assertNotIn("glossary-code", codes(data))


if __name__ == "__main__":
    unittest.main()
