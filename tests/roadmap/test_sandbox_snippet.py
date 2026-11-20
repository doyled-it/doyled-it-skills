"""The sandbox snippet in levels.md, run as written against a fake home.

It must never run the tool against the real home: not when mktemp fails, not
when it returns nothing, and not when it returns the home itself. Its listing of
touched files must reach deep config paths, and it must still list them when
the tool fails.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from helpers import SKILL

LEVELS = SKILL / "references" / "levels.md"


def snippet() -> str:
    section = LEVELS.read_text().split("## Run real tools only in a sandbox", 1)[1].split("\n## ", 1)[0]
    blocks = re.findall(r"```sh\n(.*?)```", section, re.S)
    assert len(blocks) == 1, "the sandbox section should hold exactly one sh block"
    assert "<tool> <args>" in blocks[0]
    return blocks[0]


class SandboxSnippet(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.home = self.root / "home"
        self.home.mkdir()
        (self.root / "tmp").mkdir()
        old = self.home / "old.conf"
        old.write_text("before")
        past = time.time() - 3600
        os.utime(old, (past, past))
        self.deep = self.home / "Library" / "Application Support" / "tool" / "state" / "deep.conf"
        self.marker = self.root / "tool-ran"
        self.stubs = self.root / "stubs"
        self.stubs.mkdir()

    def tool(self, exit_code=0) -> str:
        script = self.root / "tool.sh"
        script.write_text(f'echo ran > "{self.marker}"\n'
                          'touch "$HOME/in-scratch"\n'
                          f'mkdir -p "{self.deep.parent}" && touch "{self.deep}"\n'
                          f"exit {exit_code}\n")
        return f"/bin/sh {script}"

    def stub_mktemp(self, body: str) -> None:
        path = self.stubs / "mktemp"
        path.write_text("#!/bin/sh\n" + body)
        path.chmod(0o755)

    def run_snippet(self, exit_code=0):
        text = snippet().replace("<tool> <args>", self.tool(exit_code))
        env = {"HOME": str(self.home), "PATH": f"{self.stubs}:/usr/bin:/bin", "TMPDIR": str(self.root / "tmp")}
        res = subprocess.run(["/bin/sh", "-c", text], env=env, capture_output=True, text=True, timeout=60)
        found = re.search(r"^HOME=(.+)$", res.stdout, re.M)
        if found and Path(found.group(1)).name.startswith("tmp"):
            self.addCleanup(shutil.rmtree, found.group(1), True)
        return res

    def test_lists_deep_files_the_tool_touched_outside_scratch(self):
        res = self.run_snippet()
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertTrue(self.marker.exists())
        scratch = Path(re.search(r"^HOME=(.+)$", res.stdout, re.M).group(1)).resolve()
        self.assertNotEqual(scratch, self.home)
        self.assertNotIn(self.home, scratch.parents)
        self.assertTrue((scratch / "in-scratch").exists())
        self.assertIn(str(self.deep), res.stdout)
        self.assertNotIn("old.conf", res.stdout)
        self.assertNotIn("in-scratch", res.stdout)

    def test_still_lists_when_the_tool_fails(self):
        res = self.run_snippet(exit_code=3)
        self.assertEqual(res.returncode, 3)
        self.assertIn(str(self.deep), res.stdout)

    def test_refuses_to_run_when_mktemp_fails(self):
        self.stub_mktemp("exit 1\n")
        self.assert_refused(self.run_snippet())

    def test_refuses_to_run_when_mktemp_prints_nothing(self):
        self.stub_mktemp("exit 0\n")
        self.assert_refused(self.run_snippet())

    def test_refuses_to_run_when_scratch_is_the_real_home(self):
        self.stub_mktemp('printf "%s\\n" "$HOME"\n')
        self.assert_refused(self.run_snippet())

    def assert_refused(self, res):
        self.assertNotEqual(res.returncode, 0, res.stdout)
        self.assertFalse(self.marker.exists(), "the tool ran without a scratch HOME")
        self.assertFalse(self.deep.exists())
        self.assertFalse((self.home / "in-scratch").exists())


if __name__ == "__main__":
    unittest.main()
