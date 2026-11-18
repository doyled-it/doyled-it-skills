"""Only http and https links become live links, on the page, the preview and the forge."""

from __future__ import annotations

import unittest

from helpers import example, fixture, issue
from roadmaplib import blocks, checkmr, forge, model, preview, render, sync, validate
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


HOST = "https://gitlab.example.com"
ISSUE_WI = f"{HOST}/acme/search/-/work_items/12"
DEP_WI = f"{HOST}/acme/search/-/work_items/11"


def work_item_roadmap(epic_url: str) -> dict:
    """The example roadmap on a GitLab that answers web_url with /-/work_items/N (GitLab 19.5 does)."""
    data = example()
    data["forge"] = {"kind": "gitlab", "host": "gitlab.example.com", "project": "acme/search", "group": "acme"}
    data["epics"][0].update(ref="acme&10", url=epic_url)
    issue(data, "click-signals").update(ref="acme/search#11", url=DEP_WI)
    issue(data, "ranking-model").update(ref="acme/search#12", url=ISSUE_WI)
    return data


class GitLabWorkItemLinks(unittest.TestCase):
    """GitLab REST gives an issue's page as /-/work_items/N and an epic's as /groups/g/-/epics/N; its
    GraphQL names the epic /groups/g/-/work_items/N. Every one is accepted and linked as given."""

    EPIC_URLS = (f"{HOST}/groups/acme/-/epics/10", f"{HOST}/groups/acme/-/work_items/10")

    def test_validate_accepts_them(self):
        for epic_url in self.EPIC_URLS:
            with self.subTest(epic_url=epic_url):
                found = [f for f in validate.check(work_item_roadmap(epic_url)) if f.code == "bad-url"]
                self.assertEqual(found, [])

    def test_the_page_links_them(self):
        for epic_url in self.EPIC_URLS:
            with self.subTest(epic_url=epic_url):
                html = render.render_page(work_item_roadmap(epic_url))
                self.assertIn(f'href="{ISSUE_WI}"', html)
                self.assertIn(f'href="{epic_url}"', html)

    def test_the_epic_section_links_them(self):
        page = blocks.epic_block(work_item_roadmap(self.EPIC_URLS[1]), "ranking")
        self.assertIn(f'click i_ranking_model href "{ISSUE_WI}" _blank', page)
        self.assertIn(f"[acme/search#12]({ISSUE_WI})", page)
        self.assertIn(f"[acme/search#11]({DEP_WI})", page)   # in the Depends on column too

    def test_the_issue_section_takes_evidence_in_that_form(self):
        data = work_item_roadmap(self.EPIC_URLS[0])
        it = issue(data, "ranking-model")
        it["gates"] = [{"gate": "D", "passed": True, "evidence": ISSUE_WI + "#note_5", "approved_by": "the lead"},
                       "R", "M"]
        norm = model.normalize(data)
        got = issue(norm, "ranking-model")
        self.assertIn(f"({ISSUE_WI}#note_5)", blocks.issue_block(norm, got, got["gates"], "Better ranking"))


class ClosingReferencesInEitherForm(unittest.TestCase):
    """A merge request may close an issue by its /-/issues/N or its /-/work_items/N page."""

    ISSUES = f"{HOST}/acme/search/-/issues/12"

    def mr(self, text):
        return {"title": "Blend open rate", "body": text, "project": "acme/search"}

    def test_either_form_closes_the_issue(self):
        for stored, written in ((ISSUE_WI, self.ISSUES), (self.ISSUES, ISSUE_WI), (ISSUE_WI, ISSUE_WI)):
            with self.subTest(stored=stored, written=written):
                fi = {"ref": "acme/search#12", "url": stored}
                self.assertTrue(sync.closes(self.mr(f"Closes {written}"), fi, "gitlab"))

    def test_another_number_or_project_does_not(self):
        fi = {"ref": "acme/search#12", "url": ISSUE_WI}
        for written in (f"{HOST}/acme/search/-/issues/120", f"{HOST}/acme/other/-/issues/12",
                        f"{HOST}/acme/search/-/merge_requests/12", f"https://elsewhere.example/acme/search/-/issues/12"):
            with self.subTest(written=written):
                self.assertFalse(sync.closes(self.mr(f"Closes {written}"), fi, "gitlab"))

    def test_github_urls_are_not_rewritten(self):
        fi = {"ref": "o/r#12", "url": "https://github.com/o/r/issues/12"}
        self.assertFalse(sync.closes(self.mr("Closes https://github.com/o/r/-/work_items/12"), fi, "github"))

    def test_check_mr_accepts_either_form_on_the_roadmap_issue_line(self):
        got = issue(model.normalize(work_item_roadmap(f"{HOST}/groups/acme/-/epics/10")), "ranking-model")
        self.assertTrue(checkmr._named(got, f"Roadmap issue: {self.ISSUES}", None))
        got = dict(got, url=self.ISSUES)
        self.assertTrue(checkmr._named(got, f"Roadmap issue: {ISSUE_WI}", None))
        self.assertFalse(checkmr._named(got, f"Roadmap issue: {HOST}/acme/search/-/work_items/120", None))


if __name__ == "__main__":
    unittest.main()
