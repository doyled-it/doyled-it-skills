"""Diagram nodes a keyboard reaches have names; Forgejo epic members are found from mentions."""

from __future__ import annotations

import re
import unittest

from helpers import example, fixture
from roadmaplib import forge, render, sync
from test_forgejo import forgejo_roadmap
from test_publish import NoWrites


class FocusableNodesHaveNames(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = render.render_page(example())

    def test_the_diagram_is_a_group_not_an_image(self):
        svg = re.search(r"<svg class=\"flow\"[^>]*>", self.html).group(0)
        self.assertIn('role="group"', svg)
        self.assertNotIn('role="img"', svg)

    def test_every_focusable_node_has_a_role_and_a_name(self):
        links = re.findall(r"<a href=\"[^\"]+\"([^>]*)><g class=\"node", self.html)
        self.assertEqual(len(links), 2)
        for attrs in links:
            self.assertRegex(attrs, r'aria-label="[^"]+: ')
        stops = re.findall(r"<g class=\"node[^\"]*\"([^>]*tabindex=\"0\"[^>]*)>", self.html)
        self.assertEqual(len(stops), 6)
        for attrs in stops:
            self.assertIn('role="img"', attrs)
            self.assertRegex(attrs, r'aria-label="[^"]+: ')


class ForgejoMembersFromMentions(unittest.TestCase):
    def test_an_issue_that_mentions_the_parent_issue_is_reported_as_unlisted(self):
        responses = dict(fixture("forgejo_sync.json"))
        responses["GET repos/example-org/search-service/issues/10/timeline"] = [
            {"type": "issue_ref", "ref_issue": {"id": 7077, "number": 77, "title": "Add spelling suggestions",
                                                "body": "Part of #10", "state": "open", "labels": [],
                                                "html_url": "https://codeberg.org/example-org/search-service/issues/77"}},
            {"type": "pull_ref", "ref_issue": {"id": 8031, "number": 31, "title": "pr", "state": "open",
                                               "pull_request": {"merged": False}}},
            {"type": "issue_ref", "ref_issue": {"id": 9001, "number": 5, "title": "Spam", "body": "see #10",
                                                "state": "open", "labels": [],
                                                "repository": {"full_name": "stranger/elsewhere"}}}]
        fg = forge.Forgejo(NoWrites(responses), host="codeberg.org", project="example-org/search-service")
        report = sync.sync(forgejo_roadmap(), fg, orca_tasks=[], now="2026-11-17")
        found = {d.target for d in report.drift if d.kind == "unlisted-epic-issue"}
        self.assertIn("example-org/search-service#77", found)
        self.assertNotIn("example-org/search-service#31", found)
        self.assertNotIn("stranger/elsewhere#5", found)


if __name__ == "__main__":
    unittest.main()
