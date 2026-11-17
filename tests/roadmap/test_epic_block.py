"""The generated roadmap section in each epic, its local preview, and forge links on the page."""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import CLI, EXAMPLE, example, fixture, issue
from test_publish import NoWrites, Recorder
from test_sync import sync_roadmap

from roadmaplib import blocks, forge, preview, render, sync


class EpicBlock(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        data = example()
        data["page_url"] = "https://example.org/roadmap.html"
        cls.data = data
        cls.page = blocks.epic_block(data, "search-page")
        cls.mermaid = cls.page.split("```mermaid", 1)[1].split("```", 1)[0]

    def test_links_to_the_full_roadmap_page(self):
        self.assertIn("(https://example.org/roadmap.html)", self.page)
        self.assertIn("Version 3", self.page)

    def test_without_a_page_url_it_says_where_the_page_lives(self):
        text = blocks.epic_block(example(), "search-page")
        self.assertIn("kept by the program lead", text)

    def test_flowchart_has_the_epic_issues_in_a_subgraph(self):
        self.assertIn("flowchart LR", self.mermaid)
        sub = self.mermaid.split("subgraph", 1)[1].split("\n  end", 1)[0]
        for iid in ("page-design", "page-build", "page-ranking"):
            self.assertIn(iid, sub)
        self.assertNotIn("ranking-check", sub)

    def test_arrows_to_and_from_other_epics_are_dashed(self):
        self.assertIn("i_ranking_check -.-> i_page_ranking", self.mermaid)
        self.assertIn("i_page_design --> i_page_build", self.mermaid)
        # The outside issue is labelled with its epic.
        self.assertRegex(self.mermaid, r'i_ranking_check\["Better ranking: ')

    def test_status_as_color_and_words_and_gate_letters(self):
        self.assertIn("In review", self.mermaid)
        self.assertIn("classDef in_review", self.mermaid)
        self.assertIn("class i_page_design in_review", self.mermaid)
        self.assertIn("Gates: to go D R S M", self.mermaid)

    def test_status_table(self):
        table = self.page.split("| Issue | Title | Status | Gates passed | Depends on |", 1)[1]
        rows = [r for r in table.splitlines() if r.startswith("| ") and "---" not in r]
        self.assertEqual(len(rows), 3)
        self.assertIn("In review", rows[0])

    def test_published_issues_link_to_the_forge(self):
        page = blocks.epic_block(example(), "ranking")
        self.assertIn("[example-org/search-service#12](https://github.com/example-org/search-service/issues/12)", page)
        self.assertIn('click i_ranking_model href "https://github.com/example-org/search-service/issues/12"', page)

    def test_hand_written_text_outside_the_markers_is_kept(self):
        body = "Intro by hand.\n\n<!-- roadmap:epic:start -->\nstale\n<!-- roadmap:epic:end -->\n\nOutro by hand."
        new = blocks.epic_body(self.data, "search-page", body)
        self.assertTrue(new.startswith("Intro by hand.\n\n<!-- roadmap:epic:start -->"))
        self.assertTrue(new.endswith("<!-- roadmap:epic:end -->\n\nOutro by hand."))
        self.assertNotIn("stale", new)
        self.assertEqual(blocks.epic_body(self.data, "search-page", new), new)   # stable

    def test_no_em_dashes_or_milestones(self):
        self.assertNotIn("—", self.page)
        self.assertNotIn("milestone", self.page.lower())


class EpicPreview(unittest.TestCase):
    def test_preview_page_renders_mermaid_beside_the_full_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "epic-preview.html"
            res = subprocess.run([sys.executable, str(CLI), "epic-preview", str(EXAMPLE), "--epic", "search-page",
                                  "-o", str(out)], capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
            html = out.read_text()
            full = Path(tmp) / "example-roadmap.html"
            self.assertTrue(full.exists(), res.stdout)
        self.assertRegex(html, r'<script src="https://cdn\.jsdelivr\.net/npm/mermaid@\d+\.\d+\.\d+/dist/mermaid\.min\.js">')
        self.assertIn('<pre class="mermaid">', html)
        self.assertIn('<iframe', html)
        self.assertIn('src="example-roadmap.html"', html)
        self.assertIn("<table>", html)
        self.assertIn("Not written to the forge", html)

    def test_markdown_subset_is_converted_and_escaped(self):
        html = preview.markdown_to_html("**Roadmap:** [a <b>](https://x.org/?a=1&b=2) `code`\n\n"
                                        "| A | B |\n| --- | --- |\n| 1 | 2 |\n\n- [x] done item\n- [ ] open item")
        self.assertIn("<strong>Roadmap:</strong>", html)
        self.assertIn('<a href="https://x.org/?a=1&amp;b=2">a &lt;b&gt;</a>', html)
        self.assertIn("<code>code</code>", html)
        self.assertIn("<td>1</td>", html)
        self.assertIn('type="checkbox" checked disabled', html)

    def test_unknown_epic_is_an_error(self):
        res = subprocess.run([sys.executable, str(CLI), "epic-preview", str(EXAMPLE), "--epic", "nope"],
                             capture_output=True, text=True)
        self.assertEqual(res.returncode, 1)
        self.assertIn("nope", res.stdout)


class SyncEpicSections(unittest.TestCase):
    def test_read_only_sync_reports_out_of_date_sections(self):
        responses = dict(fixture("gitlab_sync.json"))
        responses["GET groups/acme/epics/10"] = {"id": 510, "iid": 10, "title": "Better ranking",
                                                 "description": "Hand text.", "web_url": "u"}
        fg = forge.GitLab(NoWrites(responses), host="h", project="acme/search", group="acme")
        report = sync.sync(sync_roadmap(), fg, orca_tasks=[], now="2026-11-17")
        self.assertTrue(any("ranking" in n and "out of date" in n for n in report.notes))

    def test_update_epics_writes_only_the_generated_section(self):
        responses = dict(fixture("gitlab_sync.json"))
        responses["GET groups/acme/epics/10"] = {"id": 510, "iid": 10, "title": "Better ranking",
                                                 "description": "Hand text.", "web_url": "u"}
        rec = Recorder(responses)
        fg = forge.GitLab(rec, host="h", project="acme/search", group="acme")
        sync.sync(sync_roadmap(), fg, orca_tasks=[], now="2026-11-17", update_epics=True)
        self.assertEqual([(m, p) for m, p, _ in rec.calls], [("PUT", "groups/acme/epics/10")])
        body = rec.calls[0][2]["description"]
        self.assertTrue(body.startswith("Hand text.\n\n<!-- roadmap:epic:start -->"))
        # The section reflects the synced status, not the stale one.
        self.assertIn("In review", body)


class PageLinks(unittest.TestCase):
    def test_every_issue_epic_merge_request_and_evidence_links_to_the_forge(self):
        data = example()
        issue(data, "ranking-model")["merge_requests"] = [
            {"ref": "example-org/search-service#31", "url": "https://github.com/example-org/search-service/pull/31",
             "state": "open", "draft": False, "pipeline": "success",
             "pipeline_url": "https://github.com/example-org/search-service/pull/31/checks"}]
        html = render.render_page(data)
        for url in ("https://github.com/example-org/search-service/issues/10",          # epic
                    "https://github.com/example-org/search-service/issues/12",          # issue
                    "https://github.com/example-org/search-service/pull/31",            # merge request
                    "https://github.com/example-org/search-service/pull/31/checks",     # pipeline
                    "https://github.com/example-org/search-service/pull/21"):           # gate evidence
            self.assertIn(f'href="{url}"', html)
        # Issue boxes in the diagram are links too.
        self.assertRegex(html, r'<a href="https://github\.com/example-org/search-service/issues/12"[^>]*><g class="node')
        self.assertIn("pipeline success", html)


if __name__ == "__main__":
    unittest.main()
