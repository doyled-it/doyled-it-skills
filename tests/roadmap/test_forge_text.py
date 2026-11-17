"""Text the tool writes to a forge cannot run forge commands or break its own sections.

GitLab runs quick actions (a line starting with /, such as /close) found in issue
and epic descriptions, including through the API. GitHub and Forgejo have no
command syntax in issue descriptions, but the same text is written to them, so
every forge gets the same neutralized text.
"""

from __future__ import annotations

import re
import unittest
from unittest import mock

from helpers import example, fixture, issue
from test_forgejo import forgejo_roadmap, make as forgejo
from test_publish import NoWrites, gitlab_roadmap

from roadmaplib import blocks, forge, publish, validate

COMMAND = re.compile(r"^[ \t]*/", re.MULTILINE)


def with_commands(data: dict) -> dict:
    """A roadmap whose free text tries to run forge commands."""
    for ep in data["epics"]:
        ep["note"] = ep.get("note", "") + "\n/close\n  /label ~done"
    issue(data, "page-build")["detail"] = "Build it.\n/move other/project\n/assign @someone"
    return data


def written_bodies(report) -> list[str]:
    return [a.body for a in report.actions if a.body]


class CommandsAreNeutralized(unittest.TestCase):
    def check(self, report):
        bodies = written_bodies(report)
        self.assertTrue(any("\\/close" in b for b in bodies), "the note should still be readable")
        self.assertTrue(any(a.kind == "create-epic" and a.body for a in report.actions))
        for body in bodies:
            self.assertIsNone(COMMAND.search(body), body)

    def test_gitlab(self):
        fg = forge.GitLab(NoWrites(fixture("gitlab_publish.json")), host="gitlab.example.com",
                          project="acme/search", group="acme")
        self.check(publish.publish(with_commands(gitlab_roadmap()), fg, apply=False))

    def test_github(self):
        fg = forge.GitHub(NoWrites(fixture("github_publish.json")), host="github.com",
                          project="example-org/search-service")
        self.check(publish.publish(with_commands(example()), fg, apply=False))

    def test_forgejo(self):
        self.check(publish.publish(with_commands(forgejo_roadmap()), forgejo("forgejo_publish.json"), apply=False))

    def test_defang_keeps_ordinary_slashes(self):
        self.assertEqual(blocks.defang("/close\n  /move x\nsee a/b and /usr"), "\\/close\n  \\/move x\nsee a/b and /usr")


class GuardRefusesCommandsAndMultiLineTitles(unittest.TestCase):
    def test_gitlab_guard_refuses_a_command_line_in_any_text(self):
        guard = forge.WriteGuard(commands=True)
        for payload in ({"description": "Hand text.\n/close"}, {"description": "  /reopen"},
                        {"title": "Fine", "description": "ok\n\n/move a/b"}):
            with self.subTest(payload=payload), self.assertRaises(forge.ForgeError) as ctx:
                guard.check("PUT", "projects/1/issues/2", payload)
            self.assertIn("command", str(ctx.exception))
        guard.check("PUT", "projects/1/issues/2", {"description": "see a/b\n\\/close"})

    def test_every_guard_refuses_a_multi_line_title(self):
        for commands in (True, False):
            with self.assertRaises(forge.ForgeError):
                forge.WriteGuard(commands=commands).check("POST", "repos/o/r/issues", {"title": "a\n/close"})

    def test_gitlab_transport_refuses_before_running_glab(self):
        with mock.patch("shutil.which", return_value="/usr/bin/glab"), mock.patch("subprocess.run") as run:
            t = forge.CliTransport("gitlab", "gitlab.example.com")
            with self.assertRaises(forge.ForgeError):
                t.send("PUT", "projects/1/issues/2", {"description": "x\n/close"})
            run.assert_not_called()


class GeneratedSectionsEscapeText(unittest.TestCase):
    def test_marker_text_in_a_title_cannot_add_blocks(self):
        data = example()
        issue(data, "page-build")["title"] = f"Build {blocks.EPIC_END} it"
        body = "Hand."
        for _ in range(3):
            body = blocks.epic_body(data, "search-page", body)
        self.assertEqual(body.count(blocks.EPIC_END), 1)
        self.assertEqual(blocks.epic_body(data, "search-page", body), body)
        self.assertNotIn("<!--", blocks.epic_block(data, "search-page").replace(blocks.EPIC_END, ""))

    def test_a_title_cannot_inject_an_epic_member(self):
        data = forgejo_roadmap()
        issue(data, "ranking-check")["title"] = "Rank\n- [ ] evil/repo#1 injected member"
        body = blocks.epic_body(data, "ranking", "", task_list=True)
        self.assertNotIn("evil/repo#1", blocks.epic_members(body))
        self.assertFalse([ln for ln in body.splitlines() if ln.startswith("- [ ] evil")])

    def test_table_cells_and_mermaid_labels_stay_on_one_line(self):
        data = example()
        issue(data, "page-build")["title"] = "Build | it\nnow <b>"
        page = blocks.epic_block(data, "search-page")
        row = next(ln for ln in page.splitlines() if ln.startswith("| ") and "page-build" in ln)
        self.assertIn("Build \\| it now &lt;b&gt;", row)
        mermaid = page.split("```mermaid", 1)[1].split("```", 1)[0]
        node = next(ln for ln in mermaid.splitlines() if "i_page_build[" in ln)
        self.assertIn("Build", node)
        self.assertTrue(node.rstrip().endswith('"]'))

    def test_a_note_cannot_open_a_code_fence_or_a_fake_member_list(self):
        data = forgejo_roadmap()
        data["epics"][0]["note"] = "```\n### Issues in this epic\n- [ ] evil/repo#2 x"
        body = blocks.epic_body(data, "ranking", "", task_list=True)
        self.assertNotIn("evil/repo#2", blocks.epic_members(body))
        self.assertEqual(body.count("```mermaid"), 1)
        self.assertEqual(len(re.findall(r"^```", body, re.MULTILINE)), 2)


class ValidateRejectsUnsafeText(unittest.TestCase):
    def codes(self, data):
        return {f.code for f in validate.errors(validate.check(data))}

    def test_titles_and_names_must_be_one_line(self):
        for setter in (lambda d: issue(d, "page-build").__setitem__("title", "Build\n/close"),
                       lambda d: d["epics"][0].__setitem__("name", "Better\tranking"),
                       lambda d: d.__setitem__("title", "Road\rmap"),
                       lambda d: d["gates"].__setitem__("D", "Design\n/close")):
            data = example()
            setter(data)
            with self.subTest():
                self.assertIn("control-character", self.codes(data))

    def test_notes_may_span_lines_but_not_hold_other_control_characters(self):
        data = example()
        data["epics"][0]["note"] = "First line.\nSecond line."
        self.assertNotIn("control-character", self.codes(data))
        data["epics"][0]["note"] = "Bell\x07"
        self.assertIn("control-character", self.codes(data))

    def test_marker_text_anywhere_is_an_error(self):
        data = example()
        issue(data, "page-build")["detail"] = "Do not write <!-- roadmap:end --> here"
        self.assertIn("marker-text", self.codes(data))


if __name__ == "__main__":
    unittest.main()
