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
from roadmaplib import blocks, forge, publish, sync, validate
from test_forgejo import forgejo_roadmap
from test_forgejo import make as forgejo
from test_publish import NoWrites, Recorder, gitlab_roadmap
from test_sync import sync_roadmap

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

    def test_defang_escapes_only_command_lines(self):
        self.assertEqual(blocks.defang("/close\n  /move x\nsee a/b and /usr\n/usr/local/bin x\n/api/v2 is slow\n/"),
                         "\\/close\n  \\/move x\nsee a/b and /usr\n/usr/local/bin x\n/api/v2 is slow\n/")


CODE_STEPS = "Steps:\n\n```\n/usr/local/bin/search-reindex --all\n/close\n```\n"


class GitLabCommandLines(unittest.TestCase):
    """Lines GitLab would run as quick actions, and only those."""

    def test_lines_gitlab_runs(self):
        for text, expected in (
                ("/close", ["/close"]),
                ("Hand text.\n/close\nmore", ["/close"]),
                ("/label ~done", ["/label ~done"]),
                ("/CLOSE", ["/CLOSE"]),
                ("/close\t", ["/close"]),
                ("```\nunclosed fence\n/close", ["/close"]),
                ("<div>\n```\n</div>\n/close\n```", ["/close"]),
                ("/assign @someone", ["/assign @someone"]),
                ("/spend 1h", ["/spend 1h"]),
                ("Notes.\n/copy_metadata #3", ["/copy_metadata #3"]),
                ("/Move group/other", ["/Move group/other"]),
        ):
            with self.subTest(text=text):
                self.assertEqual(blocks.gitlab_commands(text), expected)

    def test_lines_gitlab_does_not_run(self):
        for text in ("  /close", "see /close", "/api/v2 endpoints return 500", "/usr/local/bin/x --all", "/",
                     CODE_STEPS, "```python\n/close\n```", "<details>\n/close\n</details>", ">>>\n/close\n>>>",
                     "`/close`", "\\/close", "/etc is full", "/health returns 503", "Disk.\n/etc is full",
                     "/closed by hand", "/closeall", "/var/log is large"):
            with self.subTest(text=text):
                self.assertEqual(blocks.gitlab_commands(text), [])


class GuardRefusesCommandsAndMultiLineTitles(unittest.TestCase):
    def test_gitlab_guard_refuses_a_command_line_in_a_description(self):
        guard = forge.WriteGuard(commands=True)
        for payload in ({"description": "Hand text.\n/close"}, {"title": "Fine", "description": "ok\n\n/move a/b"}):
            with self.subTest(payload=payload), self.assertRaises(forge.ForgeError) as ctx:
                guard.check("PUT", "projects/1/issues/2", payload)
            self.assertIn("command", str(ctx.exception))
        for payload in ({"description": "see a/b\n\\/close"}, {"description": CODE_STEPS},
                        {"description": "  /reopen"}, {"title": "/api/v2 endpoints return 500", "description": "x"},
                        {"description": "/etc is full\n/health returns 503"}):
            with self.subTest(payload=payload):
                guard.check("PUT", "projects/1/issues/2", payload)

    def test_every_guard_refuses_a_multi_line_title(self):
        for commands in (True, False):
            with self.assertRaises(forge.ForgeError):
                forge.WriteGuard(commands=commands).check("POST", "repos/o/r/issues", {"title": "a\n/close"})

    def test_gitlab_transport_refuses_before_running_glab(self):
        with mock.patch("shutil.which", return_value="/usr/bin/glab"), mock.patch("subprocess.run") as run:
            t = forge.CliTransport("gitlab", "gitlab.example.com")
            run.reset_mock()   # the https check at start reads glab's own config
            with self.assertRaises(forge.ForgeError):
                t.send("PUT", "projects/1/issues/2", {"description": "x\n/close"})
            run.assert_not_called()


def small_gitlab(issue11: str, epic10: str = "Hand text.") -> tuple[dict, dict]:
    data = gitlab_roadmap()
    data["epics"] = data["epics"][:1]
    data["issues"] = [issue(data, "click-signals"), issue(data, "ranking-model")]
    responses = dict(fixture("gitlab_publish.json"))
    responses["GET projects/acme%2Fsearch/issues/11"] = dict(responses["GET projects/acme%2Fsearch/issues/11"],
                                                             description=issue11)
    responses["GET groups/acme/epics/10"] = dict(responses["GET groups/acme/epics/10"], description=epic10)
    return data, responses


class HandTextNeverStopsAWrite(unittest.TestCase):
    """Hand text the forge already holds is kept; only a live command line holds back that one write."""

    def publish(self, issue11, epic10="Hand text.", apply=True):
        data, responses = small_gitlab(issue11, epic10)
        rec = Recorder(responses)
        fg = forge.GitLab(rec if apply else NoWrites(responses), host="gitlab.example.com", project="acme/search",
                          group="acme")
        return publish.publish(data, fg, apply=apply), rec

    def test_a_code_block_or_a_path_in_hand_text_is_written(self):
        report, rec = self.publish(CODE_STEPS, epic10="Run `/close` never.\n/api/v2 notes")
        self.assertIsNone(report.failed)
        written = [b["description"] for _, p, b in rec.calls if b and "description" in b]
        self.assertTrue(any(CODE_STEPS in w for w in written))
        self.assertTrue(any(w.startswith("Run `/close` never.") for w in written))

    def test_a_path_at_the_start_of_a_line_is_not_a_command(self):
        """GitLab runs only its own command names; "/etc is full" is prose."""
        report, rec = self.publish("Anonymous counts.\n/etc is full", epic10="Plan.\n/health returns 503")
        self.assertIsNone(report.failed)
        self.assertEqual([a for a in report.actions if a.kind == "hand-fix"], [])
        written = [b["description"] for _, p, b in rec.calls if b and "description" in b]
        self.assertTrue(any("/etc is full" in w for w in written))
        self.assertTrue(any("/health returns 503" in w for w in written))

    def test_a_live_command_in_hand_text_holds_back_only_that_write(self):
        for apply in (False, True):
            with self.subTest(apply=apply):
                report, rec = self.publish("Anonymous counts.\n/close", apply=apply)
                self.assertIsNone(report.failed)
                fix = [a for a in report.actions if a.kind == "hand-fix"]
                self.assertEqual([a.target for a in fix], ["click-signals"])
                self.assertIn("/close", fix[0].detail)
                self.assertNotIn("click-signals", [a.target for a in report.actions if a.kind == "update-issue"])
                self.assertIn("update-epic", [a.kind for a in report.actions])
                if apply:
                    self.assertFalse([p for _, p, _ in rec.calls if p.endswith("/issues/11")])
                    self.assertTrue([p for _, p, _ in rec.calls if p == "groups/acme/epics/10"])

    def test_sync_skips_an_epic_with_a_live_command_and_does_not_fail(self):
        for hand, written in (("Plan.\n/close", False), (CODE_STEPS, True)):
            with self.subTest(hand=hand):
                data = sync_roadmap()
                responses = dict(fixture("gitlab_sync.json"))
                responses["GET groups/acme/epics/10"] = {"id": 510, "iid": 10, "title": "Better ranking",
                                                         "description": hand, "web_url": "https://x.example/e"}
                rec = Recorder(responses)
                fg = forge.GitLab(rec, host="gitlab.example.com", project="acme/search", group="acme")
                report = sync.sync(data, fg, orca_tasks=[], now="2026-11-17", update_epics=True)
                self.assertEqual((report.errors, report.write_errors), ([], []))
                self.assertEqual(bool(rec.calls), written)
                self.assertEqual(any(d.kind == "quick-action" and d.target == "acme&10" for d in report.drift),
                                 not written)


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
