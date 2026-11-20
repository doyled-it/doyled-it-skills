"""scripts/python.sh: run the CLI and hooks on an installed Python 3.11+, uv first, never downloading.

Each case runs the launcher with PATH set to a directory holding only the tools
that case allows: stub uv and python3 programs, a wrapper around this test's own
interpreter, and git, grep and tr. ROADMAP_UV_DIRS is empty unless a case sets
it, so the launcher cannot find a real uv outside the temporary directory.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, SCRIPTS

LAUNCHER = SCRIPTS / "python.sh"
HOOKS_JSON = ROOT / "plugins" / "roadmap" / "hooks" / "hooks.json"
FIND_ARGS = ["python", "find", "--no-project", ">=3.11"]
UV_ARGS = ["run", "--no-project", "--no-python-downloads", "--python", ">=3.11", "python"]
ROADMAP = json.dumps({"epics": [], "issues": []})


class Launcher(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.bin = self.root / "bin"
        self.work = self.root / "work"
        self.bin.mkdir()
        self.work.mkdir()
        self.uv_calls = self.root / "uv-calls"
        self.old_ran = self.root / "old-python-ran"
        self.probe = self.root / "probe.py"
        self.probe.write_text(
            "import json, sys\n"
            "print(json.dumps({'version': list(sys.version_info[:2]), 'argv': sys.argv[1:],"
            " 'stdin': sys.stdin.read()}))\n")
        for tool in ("git", "grep", "tr"):
            found = shutil.which(tool)
            if found:
                (self.bin / tool).symlink_to(found)

    def program(self, name: str, body: str, where: Path | None = None) -> Path:
        path = (where or self.bin) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("#!/bin/sh\n" + body)
        path.chmod(0o755)
        return path

    def stub_uv(self, finds=True, run_exit=0, where: Path | None = None) -> Path:
        """A uv that records each call as one line; `python find` succeeds only when finds is true."""
        return self.program("uv", f'printf "%s|" "$@" >> "{self.uv_calls}"; echo >> "{self.uv_calls}"\n'
                                  f'if [ "$1" = python ] && [ "$2" = find ]; then exit {0 if finds else 2}; fi\n'
                                  f'exit {run_exit}\n', where)

    def calls(self) -> list[list[str]]:
        if not self.uv_calls.exists():
            return []
        return [line.split("|")[:-1] for line in self.uv_calls.read_text().splitlines()]

    def real_python3(self) -> None:
        """python3 is this test's own interpreter, which is 3.11 or newer."""
        self.program("python3", f'exec "{sys.executable}" "$@"\n')

    def old_python3(self) -> None:
        self.program("python3", 'if [ "$1" = -c ]; then exit 1; fi\n'
                                 'if [ "$1" = --version ]; then echo "Python 3.9.6"; exit 0; fi\n'
                                 f'echo ran > "{self.old_ran}"\n')

    def run_launcher(self, *args, cwd=None, stdin="", env=None):
        environ = {"PATH": str(self.bin), "HOME": str(self.root), "ROADMAP_UV_DIRS": ""}
        for key, value in (env or {}).items():
            if value is None:
                environ.pop(key, None)
            else:
                environ[key] = value
        return subprocess.run(["/bin/sh", str(LAUNCHER), *args], input=stdin, text=True, capture_output=True,
                              cwd=cwd or self.work, env=environ, timeout=60)

    def test_uses_an_installed_uv_python_without_downloads(self):
        self.stub_uv()
        self.real_python3()
        for mode in ([], ["--hook"]):
            with self.subTest(mode=mode):
                self.uv_calls.unlink(missing_ok=True)
                res = self.run_launcher(*mode, str(self.probe), "validate", "roadmap.json")
                self.assertEqual(res.returncode, 0, res.stderr)
                self.assertEqual(self.calls(), [FIND_ARGS, UV_ARGS + [str(self.probe), "validate", "roadmap.json"]])

    def test_falls_back_to_python3_when_uv_has_no_python_installed(self):
        self.stub_uv(finds=False)
        self.real_python3()
        res = self.run_launcher(str(self.probe), "validate", "roadmap.json")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(json.loads(res.stdout)["argv"], ["validate", "roadmap.json"])
        self.assertEqual(self.calls(), [FIND_ARGS], "uv must not run, or download, when it has no Python")

    def test_falls_back_to_python3_when_it_is_3_11_or_newer(self):
        self.real_python3()
        res = self.run_launcher(str(self.probe), "validate", "roadmap.json")
        self.assertEqual(res.returncode, 0, res.stderr)
        out = json.loads(res.stdout)
        self.assertGreaterEqual(tuple(out["version"]), (3, 11))
        self.assertEqual(out["argv"], ["validate", "roadmap.json"])

    def test_finds_uv_in_the_usual_places_when_path_lacks_it(self):
        self.real_python3()
        uv = self.stub_uv(where=self.root / ".local" / "bin")
        res = self.run_launcher(str(self.probe), env={"ROADMAP_UV_DIRS": None})
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(self.calls()[0], FIND_ARGS)
        self.uv_calls.unlink()
        other = self.root / "tools"
        self.stub_uv(where=other)
        uv.unlink()
        res = self.run_launcher(str(self.probe), env={"ROADMAP_UV_DIRS": f"{self.root / 'none'}:{other}"})
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(self.calls()[0], FIND_ARGS)

    def test_hook_mode_passes_the_payload_and_drops_its_flag(self):
        self.real_python3()
        res = self.run_launcher("--hook", str(self.probe), "stop", stdin='{"hook_event_name": "Stop"}')
        self.assertEqual(res.returncode, 0, res.stderr)
        out = json.loads(res.stdout)
        self.assertEqual(out["argv"], ["stop"])
        self.assertEqual(out["stdin"], '{"hook_event_name": "Stop"}')

    def test_old_python3_is_refused_with_a_clear_message(self):
        self.old_python3()
        res = self.run_launcher(str(self.probe), "validate", "roadmap.json")
        self.assertEqual(res.returncode, 1)
        self.assertFalse(self.old_ran.exists(), "the script must not run on Python 3.9")
        for words in ("Python 3.11 or newer", "uv", "Python 3.9.6"):
            self.assertIn(words, res.stderr)

    def test_uv_without_python_is_refused_without_a_download(self):
        uv = self.stub_uv(finds=False)
        self.old_python3()
        res = self.run_launcher(str(self.probe))
        self.assertEqual(res.returncode, 1)
        self.assertEqual(self.calls(), [FIND_ARGS])
        self.assertIn("uv python install", res.stderr)
        self.assertIn(str(uv), res.stderr)

    def test_no_python_at_all_is_refused_with_a_clear_message(self):
        res = self.run_launcher(str(self.probe))
        self.assertEqual(res.returncode, 1)
        self.assertIn("Python 3.11 or newer", res.stderr)
        self.assertIn("no python3", res.stderr)

    def test_hook_mode_stays_silent_without_a_roadmap(self):
        self.old_python3()
        res = self.run_launcher("--hook", str(self.probe), "post-tool-use", stdin="{}")
        self.assertEqual((res.returncode, res.stdout, res.stderr), (0, "", ""))

    def test_hook_mode_stays_silent_for_another_tools_roadmap_json(self):
        self.old_python3()
        (self.work / "roadmap.json").write_text(json.dumps({"milestones": []}))
        res = self.run_launcher("--hook", str(self.probe), "stop", stdin="{}")
        self.assertEqual((res.returncode, res.stdout, res.stderr), (0, "", ""))

    def test_hook_mode_fails_open_with_one_warning_when_a_roadmap_is_present(self):
        self.old_python3()
        repo = self.root / "repo"
        (repo / "sub").mkdir(parents=True)
        (repo / "roadmap.json").write_text(ROADMAP)
        subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True)
        (self.root / "elsewhere.json").write_text(ROADMAP)
        cases = {
            "working directory": dict(cwd=repo),
            "git root": dict(cwd=repo / "sub"),
            "ROADMAP_FILE": dict(env={"ROADMAP_FILE": str(self.root / "elsewhere.json")}),
        }
        for name, kw in cases.items():
            with self.subTest(found_by=name):
                res = self.run_launcher("--hook", str(self.probe), "stop", stdin="{}", **kw)
                self.assertEqual(res.returncode, 0, res.stderr)
                message = json.loads(res.stdout)["systemMessage"]
                self.assertIn("roadmap check skipped", message)
                self.assertIn("Python 3.11 or newer", message)
                self.assertIn("uv", message)

    def test_hook_mode_names_the_uv_it_tried(self):
        uv = self.stub_uv(finds=False)
        self.old_python3()
        (self.work / "roadmap.json").write_text(ROADMAP)
        res = self.run_launcher("--hook", str(self.probe), "stop", stdin="{}")
        self.assertEqual(res.returncode, 0)
        message = json.loads(res.stdout)["systemMessage"]
        self.assertIn(str(uv), message)
        self.assertIn("uv python install", message)
        self.assertEqual(self.calls(), [FIND_ARGS], "a hook must never start a Python download")

    def test_hook_mode_never_returns_a_blocking_exit_code(self):
        """uv exits 2 when it cannot run; exit 2 would block a Claude Code turn."""
        self.stub_uv(run_exit=2)
        (self.work / "roadmap.json").write_text(ROADMAP)
        res = self.run_launcher("--hook", str(self.probe), "stop", stdin="{}")
        self.assertEqual(res.returncode, 0)
        self.assertIn("roadmap check skipped", json.loads(res.stdout)["systemMessage"])
        (self.work / "roadmap.json").unlink()
        res = self.run_launcher("--hook", str(self.probe), "stop", stdin="{}")
        self.assertEqual((res.returncode, res.stdout), (0, ""))

    def test_cli_mode_keeps_the_script_exit_status(self):
        self.real_python3()
        failing = self.root / "fails.py"
        failing.write_text("import sys\nsys.exit(3)\n")
        self.assertEqual(self.run_launcher(str(failing)).returncode, 3)


class HookCommands(unittest.TestCase):
    def test_every_hook_runs_through_the_launcher(self):
        prefix = ('sh "${CLAUDE_PLUGIN_ROOT}/skills/roadmap/scripts/python.sh" --hook '
                  '"${CLAUDE_PLUGIN_ROOT}/hooks/roadmap_hook.py" ')
        hooks = json.loads(HOOKS_JSON.read_text())["hooks"]
        commands = [h["command"] for event in hooks.values() for entry in event for h in entry["hooks"]]
        self.assertEqual(len(commands), 2)
        for command in commands:
            self.assertTrue(command.startswith(prefix), command)
            self.assertNotIn("python3", command)

    def test_launcher_is_posix_sh_and_executable(self):
        self.assertTrue(LAUNCHER.read_text().startswith("#!/bin/sh\n"))
        self.assertTrue(os.access(LAUNCHER, os.X_OK))


if __name__ == "__main__":
    unittest.main()
