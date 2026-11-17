"""render: the one-page HTML roadmap (structure, not pixels)."""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

from helpers import CLI, EXAMPLE, example, issue

from roadmaplib import render


class Tags(HTMLParser):
    """Collects start tags with their attributes, and visible text."""

    def __init__(self):
        super().__init__()
        self.tags: list[tuple[str, dict]] = []
        self.text: list[str] = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))

    def handle_data(self, data):
        self.text.append(data)

    def having(self, tag, cls=None):
        return [a for t, a in self.tags
                if t == tag and (cls is None or cls in (a.get("class") or "").split())]


def parse(html: str) -> Tags:
    p = Tags()
    p.feed(html)
    return p


class RenderStructure(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = render.render_page(example())
        cls.doc = parse(cls.html)

    def test_page_basics_and_title(self):
        self.assertTrue(self.html.startswith("<!DOCTYPE html>"))
        self.assertIn('<html lang="en">', self.html)
        self.assertIn("<title>Search service roadmap</title>", self.html)
        self.assertIn('name="viewport"', self.html)

    def test_one_lane_per_epic_with_names(self):
        self.assertEqual(len(self.doc.having("rect", "lane")), 3)
        text = " ".join(self.doc.text)
        for name in ("Better ranking", "New search page", "Safe weekly releases"):
            self.assertIn(name, text)

    def test_one_focusable_node_per_issue_with_status_class(self):
        nodes = self.doc.having("g", "node")
        self.assertEqual(len(nodes), 8)
        for n in nodes:
            self.assertEqual(n.get("tabindex"), "0")
        classes = {c for n in nodes for c in n["class"].split()}
        self.assertTrue({"done", "prog", "review", "block", "todo"} <= classes)

    def test_dependency_arrows_and_dashed_cross_epic_arrows(self):
        edges = self.doc.having("path", "edge")
        deps = sum(len(i["depends_on"]) for i in example()["issues"])
        self.assertEqual(len(edges), deps)
        cross = self.doc.having("path", "cross")
        # page-ranking <- ranking-check, weekly-release <- click-signals
        self.assertEqual(len(cross), 2)
        self.assertRegex(self.html, r"\.edge\.cross[^{]*\{[^}]*stroke-dasharray")

    def test_gates_show_passed_state(self):
        passed = self.doc.having("g", "passed")
        # click-signals D R M, ranking-model D
        self.assertEqual(len(passed), 4)
        self.assertIn("gate passed", self.html)

    def test_legend_lists_every_gate_and_status(self):
        legend = self.html.split('class="legend"', 1)[1].split("</section>", 1)[0]
        for letter in ("D", "R", "S", "M", "U"):
            self.assertIn(f">{letter}</span>", legend)
        for label in ("To do", "In progress", "In review", "Blocked", "Done"):
            self.assertIn(label, legend)
        self.assertIn("Depends on", legend)
        self.assertIn("another epic", legend)

    def test_right_now_panel(self):
        now = self.html.split('id="right-now"', 1)[1].split("</section>", 1)[0]
        self.assertIn("ranking-model", now)       # in progress
        self.assertIn("page-design", now)         # in review
        self.assertIn("release-checks", now)      # blocked
        ready = now.split("Ready to start", 1)[1].split("</div>", 1)[0]
        self.assertNotIn("page-build", ready)     # waits on page-design
        self.assertIn("Waiting on dependencies", now)

    def test_issue_tables_per_epic_link_published_issues(self):
        tables = self.doc.having("table")
        self.assertEqual(len(tables), 3)
        self.assertIn('href="https://github.com/example-org/search-service/issues/12"', self.html)
        self.assertIn("example-org/search-service#12", self.html)
        self.assertIn('scope="row"', self.html)
        self.assertIn("Iteration 2", self.html)

    def test_epic_link_when_published(self):
        self.assertIn('href="https://github.com/example-org/search-service/issues/10"', self.html)

    def test_timeline(self):
        self.assertEqual(len(self.doc.having("time")), 2)

    def test_light_and_dark_and_accessible(self):
        self.assertIn("prefers-color-scheme: dark", self.html)
        svg = self.doc.having("svg", "flow")[0]
        self.assertEqual(svg.get("role"), "img")
        self.assertTrue(svg.get("aria-label"))
        self.assertEqual(self.html.count("<title>"), 1 + 8)  # page title + one per node

    def test_agreed_state_shown(self):
        self.assertIn("Agreed with the program lead", self.html)

    def test_no_project_specifics_or_banned_text(self):
        for word in ("mdoyle", "ep2p", "CDP", "gemma", "—"):
            self.assertNotIn(word, self.html)


class RenderVariants(unittest.TestCase):
    def test_draft_roadmap_says_so(self):
        data = example()
        data["agreed"] = False
        self.assertIn("Draft, not yet agreed", render.render_page(data))

    def test_text_is_escaped(self):
        data = example()
        issue(data, "page-build")["title"] = "<script>alert(1)</script>"
        html = render.render_page(data)
        self.assertNotIn("<script>alert", html)
        self.assertIn("&lt;script&gt;", html)

    def test_structural_errors_stop_rendering(self):
        data = example()
        issue(data, "click-signals")["depends_on"] = ["page-ranking"]
        with self.assertRaises(render.RenderError):
            render.render_page(data)

    def test_epic_with_no_issues_still_gets_a_lane(self):
        data = example()
        data["epics"].append({"id": "later", "name": "Later work"})
        html = render.render_page(data)
        self.assertEqual(len(parse(html).having("rect", "lane")), 4)


class RenderCommand(unittest.TestCase):
    def test_writes_html_next_to_json_by_default_or_to_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "page.html"
            res = subprocess.run([sys.executable, str(CLI), "render", str(EXAMPLE), "-o", str(out)],
                                 capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertTrue(out.read_text().startswith("<!DOCTYPE html>"))
            self.assertRegex(res.stdout, re.compile(r"wrote .*page\.html \(8 issues, 3 epics\)"))


if __name__ == "__main__":
    unittest.main()
