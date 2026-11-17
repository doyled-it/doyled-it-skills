"""Only http and https links become live links, on the page, the preview and the forge."""

from __future__ import annotations

import unittest

from helpers import example, fixture, issue
from roadmaplib import blocks, forge, model, preview, render, validate
from test_publish import NoWrites

BAD = "javascript:alert(1)"


def roadmap_with_bad_links() -> dict:
    data = example()
    data["page_url"] = BAD
    data["epics"][0]["url"] = BAD
    it = issue(data, "ranking-model")
    it["url"] = BAD
    it["links"] = [BAD, {"label": "notes", "url": "JavaScript:alert(2)"}, {"label": "data", "url": "data:text/html,x"}]
    it["gates"] = [{"gate": "D", "passed": True, "evidence": BAD, "approved_by": "the program lead"}, "R", "M"]
    it["merge_requests"] = [{"ref": "o/r#31", "url": BAD, "state": "open", "pipeline": "success",
                             "pipeline_url": "vbscript:x"}]
    return data


class ValidateRejectsUnsafeLinks(unittest.TestCase):
    def test_every_link_field_must_be_http_or_https(self):
        found = [f.where for f in validate.check(roadmap_with_bad_links()) if f.code == "bad-url"]
        for where in ("page_url", "epics[ranking].url", "issues[ranking-model].url",
                      "issues[ranking-model].links[0]", "issues[ranking-model].links[1].url",
                      "issues[ranking-model].links[2].url", "issues[ranking-model].gates[D].evidence",
                      "issues[ranking-model].merge_requests[0].url",
                      "issues[ranking-model].merge_requests[0].pipeline_url"):
            self.assertIn(where, found)

    def test_ordinary_links_pass(self):
        self.assertFalse([f for f in validate.check(example()) if f.code == "bad-url"])


class PageHasNoUnsafeLinks(unittest.TestCase):
    def test_render(self):
        html = render.render_page(roadmap_with_bad_links())
        for scheme in ("javascript:", "vbscript:", "data:"):
            self.assertNotIn(f'href="{scheme}', html.lower())
        self.assertIn("o/r#31", html)            # the text is still shown

    def test_preview_markdown(self):
        html = preview.markdown_to_html("[x](javascript:onerror=alert;throw/XSS/) and [ok](https://example.org/a)")
        self.assertNotIn('href="javascript:', html)
        self.assertIn('<a href="https://example.org/a">ok</a>', html)

    def test_generated_sections(self):
        data = roadmap_with_bad_links()
        page = blocks.epic_block(data, "ranking")
        self.assertNotIn("javascript:", page)
        norm = model.normalize(data)
        it = issue(norm, "ranking-model")
        self.assertNotIn("javascript:", blocks.issue_block(norm, it, it["gates"], "Better ranking"))

    def test_forgejo_commit_status_link_must_be_http(self):
        responses = fixture("forgejo_sync.json")
        responses["GET repos/example-org/search-service/commits/abc123/status"] = {
            "state": "success", "statuses": [{"target_url": BAD}]}
        fg = forge.Forgejo(NoWrites(responses), host="codeberg.org", project="example-org/search-service")
        pr = fg.related_mrs({"project": "example-org/search-service", "number": 12})[0]
        self.assertTrue(pr["pipeline_url"].startswith("https://"))


if __name__ == "__main__":
    unittest.main()
