"""validate reports wrong types instead of crashing, handles deep chains, and knows technical words."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from helpers import example, issue

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
