"""validate: issue and epic references are checked with the forge's own patterns."""

from __future__ import annotations

import unittest

from helpers import example, issue
from roadmaplib import validate


def errors(data):
    return {f.code for f in validate.check(data) if f.level == "error"}


def with_refs(kind, epic_ref, issue_ref):
    data = example()
    data["forge"] = {"kind": kind}
    data["epics"][0]["ref"] = epic_ref
    issue(data, "page-build")["ref"] = issue_ref
    return data


class ForgeShapedRefs(unittest.TestCase):
    def test_an_issue_ref_with_an_epic_ampersand_is_rejected(self):
        for kind in ("gitlab", "github", "forgejo"):
            data = with_refs(kind, "o/r&5" if kind == "gitlab" else "o/r#5", "o/r&7")
            self.assertIn("bad-ref", errors(data), kind)

    def test_gitlab_epic_refs_use_ampersand_only(self):
        self.assertNotIn("bad-ref", errors(with_refs("gitlab", "grp/sub&5", "grp/proj#7")))
        self.assertIn("bad-ref", errors(with_refs("gitlab", "grp/sub#5", "grp/proj#7")))

    def test_github_and_forgejo_epics_are_issues_so_they_use_hash(self):
        for kind in ("github", "forgejo", "gitea"):
            self.assertNotIn("bad-ref", errors(with_refs(kind, "o/r#5", "o/r#7")), kind)
            self.assertIn("bad-ref", errors(with_refs(kind, "o/r&5", "o/r#7")), kind)

    def test_without_a_forge_an_epic_ref_may_use_either_mark(self):
        data = example()
        data.pop("forge", None)
        data["epics"][0]["ref"] = "o/r&5"
        issue(data, "page-build")["ref"] = "o/r#7"
        self.assertNotIn("bad-ref", errors(data))
        data["epics"][0]["ref"] = "o/r#5"
        self.assertNotIn("bad-ref", errors(data))


if __name__ == "__main__":
    unittest.main()
