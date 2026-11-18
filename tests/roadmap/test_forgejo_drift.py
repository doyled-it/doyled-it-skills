"""Forgejo: the tool's own drift issue is never an epic member, and its text does not mention issues."""

from __future__ import annotations

import unittest

import helpers  # noqa: F401  (puts the roadmap scripts on sys.path)
from roadmaplib import blocks, forge

P = "example-org/search-service"


def mention(number, title, body="", state="open"):
    return {"ref_issue": {"id": 8000 + number, "number": number, "title": title, "body": body, "state": state,
                          "labels": [], "updated_at": "2026-11-16T10:00:00Z",
                          "html_url": f"https://codeberg.org/{P}/issues/{number}"}}


def members(timeline):
    responses = {f"GET repos/{P}/issues/10/timeline": timeline}
    fg = forge.Forgejo(forge.RecordedTransport(responses), host="codeberg.org", project=P)
    epic = {"ref": f"{P}#10", "number": 10, "body": ""}
    return {i["number"] for i in fg.epic_issues(epic)}


class DriftIssueIsNotAMember(unittest.TestCase):
    def test_the_drift_issue_mentioning_the_epic_is_not_an_unlisted_member(self):
        drift = mention(50, forge.DRIFT_TITLE, forge.drift_body("- **x** note about #10"))
        self.assertEqual(members([drift, mention(60, "A real child", "Part of #10")]), {60})

    def test_a_plain_issue_with_a_similar_title_still_counts(self):
        self.assertEqual(members([mention(51, forge.DRIFT_TITLE, "no markers here")]), {51})


class HashIsEscapedInGeneratedText(unittest.TestCase):
    def test_md_inline_escapes_issue_references(self):
        out = blocks.md_inline("example-org/search-service#99 and #10")
        self.assertNotIn("#", out.replace("\\#", ""))
        self.assertIn("\\#99", out)


if __name__ == "__main__":
    unittest.main()
