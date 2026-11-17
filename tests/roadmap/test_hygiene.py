"""Guards that run before any forge call, pages that stay local, and preview files that never clobber."""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fakeforge import FakeGitHub, github
from helpers import CLI, EXAMPLE, example
from roadmaplib import forge, preview, publish, render

SRI = "sha384-rbtjAdnIQE/aQJGEgXrVUlMibdfTSa4PQju4HDhN3sR2PmaKFzhEafuePsl9H/9I"


class GuardsRunBeforeTheForge(unittest.TestCase):
    def test_glab_and_gh_are_never_run_for_a_delete_or_a_close(self):
        for kind in ("gitlab", "github"):
            with mock.patch("shutil.which", return_value=f"/usr/bin/{kind}"), \
                    mock.patch("subprocess.run") as run:
                t = forge.CliTransport(kind, None)
                run.reset_mock()   # the https check at start reads glab's own config
                for method, body in (("DELETE", None), ("PUT", {"state_event": "close"}),
                                     ("PATCH", {"state": "closed"})):
                    with self.subTest(kind=kind, method=method), self.assertRaises(forge.ForgeError):
                        t.send(method, "projects/1/issues/2", body)
                run.assert_not_called()

    def test_a_full_apply_never_closes_or_deletes(self):
        fake = FakeGitHub()
        fake.add_issue("example-org/search-service", 10, "Better ranking")
        fake.add_issue("example-org/search-service", 11, "Record which results people open", state="closed")
        fake.add_issue("example-org/search-service", 12, "Rank results by open rate")
        publish.publish(example(), github(fake), apply=True)
        self.assertTrue(fake.writes)
        for method, _path, body in fake.writes:
            self.assertNotEqual(method, "DELETE")
            self.assertNotIn("state", body or {})
        self.assertEqual(fake.issues[("example-org/search-service", 11)]["state"], "closed")


class PagesStayLocal(unittest.TestCase):
    def test_the_roadmap_page_loads_nothing_from_elsewhere(self):
        html = render.render_page(example())
        self.assertNotIn("fonts.googleapis", html)
        self.assertFalse(re.findall(r"<(?:link|script)[^>]+(?:href|src)=\"https?://", html))
        self.assertIn('<meta name="generator" content="roadmap render">', html)

    def test_the_preview_pins_mermaid_with_an_integrity_hash(self):
        html = preview.preview_page(example(), "search-page", "full.html")
        script = re.search(r"<script src=\"https://cdn\.jsdelivr\.net/npm/mermaid@11\.4\.1[^>]*>", html).group(0)
        self.assertIn(f'integrity="{SRI}"', script)
        self.assertIn('crossorigin="anonymous"', script)
        self.assertIn('referrerpolicy="no-referrer"', script)


class PreviewNeverClobbers(unittest.TestCase):
    def run_preview(self, out):
        return subprocess.run([sys.executable, str(CLI), "epic-preview", str(EXAMPLE), "--epic", "search-page",
                               "-o", str(out)], capture_output=True, text=True)

    def test_out_elsewhere_keeps_a_file_named_like_the_roadmap(self):
        with tempfile.TemporaryDirectory() as tmp:
            keep = Path(tmp) / "example-roadmap.html"
            keep.write_text("precious")
            res = self.run_preview(Path(tmp) / "x.html")
            self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
            self.assertEqual(keep.read_text(), "precious")
            self.assertTrue((Path(tmp) / "x-full.html").exists())
            self.assertIn('src="x-full.html"', (Path(tmp) / "x.html").read_text())

    def test_an_existing_file_it_did_not_write_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            other = Path(tmp) / "x-full.html"
            other.write_text("someone else's page")
            res = self.run_preview(Path(tmp) / "x.html")
            self.assertEqual(res.returncode, 1)
            self.assertEqual(other.read_text(), "someone else's page")
            self.assertIn("x-full.html", res.stdout)


class DocsListEveryCommand(unittest.TestCase):
    def test_the_command_docstring_names_every_subcommand(self):
        from roadmaplib import cli

        commands = set(cli.build_parser()._subparsers._group_actions[0].choices)
        doc = CLI.read_text().split('"""')[1]
        listed = set(re.findall(r"^  ([a-z][a-z-]+) ROADMAP", doc, re.MULTILINE))
        self.assertEqual(listed, commands)


if __name__ == "__main__":
    unittest.main()
